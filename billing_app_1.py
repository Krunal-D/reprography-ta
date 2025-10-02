from flask import Flask, request, render_template_string, redirect, url_for, jsonify
from datetime import date
import os 
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, Text
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func
from sqlalchemy.engine.url import URL # Added for robust URL handling

# Initialize the Flask application
app = Flask(__name__)

# --- SQLAlchemy Database Setup ---
# 1. Dynamic Database URL
# Uses the DATABASE_URL environment variable set on Render/Supabase, 
# or falls back to local SQLite for development.
DATABASE_URL = os.environ.get(
    "DATABASE_URL", 
    "sqlite:///billing.db"
)

# 2. Configure Engine
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """Helper function to get and close a database session."""
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()

# --- Model Definitions (Your Tables as SQLAlchemy Classes) ---
class Bill(Base):
    __tablename__ = 'bills'
    id = Column(Integer, primary_key=True)
    bill_display_id = Column(Text, unique=True, index=True)
    bill_date = Column(Text, nullable=False)
    recipient = Column(Text)
    prepared_by = Column(Text)
    checked_by = Column(Text)
    fic_reprography = Column(Text)
    items = relationship("BillItem", back_populates="bill", cascade="all, delete-orphan")

class BillItem(Base):
    __tablename__ = 'bill_items'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    units = Column(Integer, nullable=False)
    rate = Column(Float, nullable=False)
    amount = Column(Float, nullable=False)
    bill_id = Column(Integer, ForeignKey('bills.id'), nullable=False)
    bill = relationship("Bill", back_populates="items")

class Product(Base):
    __tablename__ = 'products'
    item_code = Column(Text, primary_key=True)
    item_name = Column(Text, nullable=False)
    default_rate = Column(Float)

def init_db():
    """Initializes schema and seeds initial products if the table is empty."""
    # This creates the tables in the database (SQLite locally, Postgres remotely)
    Base.metadata.create_all(bind=engine) 

    db = get_db()
    try:
        # Check if products table is empty before seeding
        if db.query(Product).count() == 0:
            print("Seeding initial products...")
            sample_products = [
                Product(item_code='0000', item_name='Custom Item', default_rate=0.00),
                Product(item_code='0001', item_name='A4 Plain Paper Ream', default_rate=350.00),
                Product(item_code='0002', item_name='Official Envelope (Pack of 100)', default_rate=150.00),
                Product(item_code='0003', item_name='Spiral Binding Service', default_rate=50.00),
                Product(item_code='0004', item_name='Color Printout (A4)', default_rate=10.00)
            ]
            db.add_all(sample_products)
            db.commit()
            print("Products seeded successfully.")
    except Exception as e:
        db.rollback()
        print(f"Error initializing products: {e}")
    finally:
        db.close()
        
# --- HTML & CSS Template ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Interactive Billing System</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @page {
            size: A5;
            margin: 0;
        }
        @media print {
            body { 
                background: white !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
            }
            .no-print {
                display: none !important;
            }
            .print-container {
                transform: scale(0.95);
                transform-origin: top left;
                width: 100%;
                height: 100%;
            }
            #bill-section {
                box-shadow: none !important;
                border: 1px solid #ccc !important;
                page-break-inside: avoid;
            }
            .header-logo-print {
                height: 3.5rem;
                margin-right: 1rem;
            }
            .signature-container-print {
                margin-top: 2rem !important;
            }
            .signature-grid-print {
                display: flex !important;
                justify-content: space-between !important;
                gap: 1.5rem !important;
            }
            .signature-grid-print > div {
                flex: 1;
            }
            .overflow-x-auto {
                overflow-x: visible !important;
            }
            .rate-column {
                display: none !important;
            }
            .print-only-tfoot {
                display: table-footer-group;
            }
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(-10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .fade-in { animation: fadeIn 0.5s ease-out forwards; }
        
        .print-only-tfoot {
            display: none;
        }
    </style>
</head>
<body class="bg-gray-100 text-gray-800 font-sans">
    <div class="print-container">
        <div class="container mx-auto p-4 md:p-8 max-w-4xl">
            <div class="bg-white rounded-lg shadow-md p-6 mb-8 no-print fade-in" style="animation-delay: 0.1s;">
                <h2 class="text-2xl font-semibold mb-4 border-b pb-2">Add Billing Item</h2>
                <form action="/add" method="post" class="grid grid-cols-1 md:grid-cols-6 gap-4 items-end">
                    <input type="hidden" name="bill_id" value="{{ bill.id }}">
                    
                    <div class="md:col-span-1">
                        <label for="item_code" class="block text-sm font-medium text-gray-600">Item Code</label>
                        <select id="item_code" class="mt-1 block w-full px-3 py-2 bg-white border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500">
                            <option value="" disabled selected>Select</option>
                            {% for code, data in item_codes.items() %}
                            <option value="{{ code }}">{{ code }}</option>
                            {% endfor %}
                        </select>
                    </div>

                    <div class="md:col-span-2">
                        <label for="item_name" class="block text-sm font-medium text-gray-600">Item Name</label>
                        <input type="text" id="item_name" name="item_name" required readonly
                               class="mt-1 block w-full px-3 py-2 bg-gray-100 border border-gray-300 rounded-md shadow-sm cursor-not-allowed">
                    </div>
                    
                    <div>
                        <label for="units" class="block text-sm font-medium text-gray-600">Units</label>
                        <input type="number" id="units" name="units" required min="1" value="1"
                               class="mt-1 block w-full px-3 py-2 bg-white border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500">
                    </div>

                    <div>
                        <label for="rate" class="block text-sm font-medium text-gray-600">Rate</label>
                        <input type="number" id="rate" name="rate" required min="0" step="0.01" value="0.00"
                               class="mt-1 block w-full px-3 py-2 bg-white border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500">
                    </div>

                    <div class="md:col-span-1">
                        <label for="amount" class="block text-sm font-medium text-gray-600">Amount</label>
                        <input type="number" id="amount" name="amount" required readonly
                               class="mt-1 block w-full px-3 py-2 bg-gray-100 border border-gray-300 rounded-md shadow-sm cursor-not-allowed">
                    </div>
                    
                    <div class="md:col-start-6">
                        <button type="submit" class="w-full bg-indigo-600 text-white font-bold py-2 px-4 rounded-md hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition">
                            Add Item
                        </button>
                    </div>
                </form>
            </div>

            <div id="bill-section" class="bg-white rounded-lg shadow-lg p-6 fade-in" style="animation-delay: 0.2s;">
                <div class="flex justify-between items-start mb-4">                
                    <img src="{{ url_for('static', filename='Reprography_logo.svg') }}" alt="Reprography Logo" class="h-20 mr-6 header-logo-print">       
                    <div class="text-right text-sm">
                        <div class="flex items-center justify-end">
                            <label for="bill_no" class="font-bold mr-2">Bill No:</label>
                            <input type="text" id="bill_no" value="{{ bill.bill_display_id }}" data-bill-id="{{ bill.id }}" data-field="bill_display_id" class="w-24 p-1 border rounded bg-white font-semibold bill-field">
                        </div>
                        <div class="flex items-center justify-end mt-1">
                            <label for="bill_date" class="font-bold mr-2">Date:</label>
                            <input type="date" id="bill_date" value="{{ bill.bill_date }}" data-bill-id="{{ bill.id }}" data-field="bill_date" class="w-32 p-1 border rounded bill-field">
                        </div>
                    </div>
                </div>

                <div class="flex items-center mb-6 border-b pb-4">
                    <label for="recipient" class="font-bold mr-2 text-gray-700">To,</label>
                    <input type="text" id="recipient" placeholder="Enter recipient name or department..." value="{{ bill.recipient or '' }}" data-bill-id="{{ bill.id }}" data-field="recipient" class="w-full p-1 border-0 border-b-2 border-gray-200 focus:ring-0 focus:border-indigo-500 bill-field">
                </div>

                {% if items %}
                    <div class="overflow-x-auto -mx-6">
                        <table class="min-w-full divide-y divide-gray-200">
                            <thead class="bg-gray-50">
                                <tr>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">S. No.</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Particulars</th>
                                    <th class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Units</th>
                                    <th class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider rate-column">Rate</th>
                                    <th class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Amount</th>
                                </tr>
                            </thead>
                            <tbody class="bg-white divide-y divide-gray-200">
                                {% for item in items %}
                                <tr>
                                    <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{{ loop.index }}</td>
                                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-700">{{ item.name }}</td>
                                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-700 text-right">{{ item.units }}</td>
                                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-700 text-right rate-column">₹{{ "%.2f"|format(item.rate) }}</td>
                                    <td class="px-6 py-4 whitespace-nowrap text-sm font-semibold text-gray-900 text-right">₹{{ "%.2f"|format(item.amount) }}</td>
                                </tr>
                                {% endfor %}
                            </tbody>
                            <tfoot class="bg-gray-50 no-print">
                                <tr>
                                    <td colspan="4" class="px-6 py-4 text-right text-sm font-bold text-gray-700 uppercase">Total</td>
                                    <td class="px-6 py-4 text-right text-sm font-bold text-gray-900">₹{{ "%.2f"|format(total_amount) }}</td>
                                </tr>
                            </tfoot>
                            <tfoot class="bg-gray-50 print-only-tfoot">
                                <tr>
                                    <td colspan="3" class="px-6 py-4 text-right text-sm font-bold text-gray-700 uppercase">Total</td>
                                    <td class="px-6 py-4 text-right text-sm font-bold text-gray-900">₹{{ "%.2f"|format(total_amount) }}</td>
                                </tr>
                            </tfoot>
                        </table>
                    </div>
                    
                    <div class="mt-16 pt-6 border-t border-gray-200 signature-container-print">
                        <div class="grid grid-cols-1 md:grid-cols-3 gap-10 text-center signature-grid-print">
                            <div>
                                <input type="text" value="{{ bill.prepared_by or '' }}" data-bill-id="{{ bill.id }}" data-field="prepared_by" class="w-full bg-transparent border-b-2 border-gray-300 focus:outline-none focus:border-indigo-500 text-center py-1 signature-input bill-field">
                                <label class="block text-sm font-semibold text-gray-600 mt-2">Prepared by</label>
                            </div>
                            <div>
                                <input type="text" value="{{ bill.checked_by or '' }}" data-bill-id="{{ bill.id }}" data-field="checked_by" class="w-full bg-transparent border-b-2 border-gray-300 focus:outline-none focus:border-indigo-500 text-center py-1 signature-input bill-field">
                                <label class="block text-sm font-semibold text-gray-600 mt-2">Checked By</label>
                            </div>
                            <div>
                                <input type="text" value="{{ bill.fic_reprography or '' }}" data-bill-id="{{ bill.id }}" data-field="fic_reprography" class="w-full bg-transparent border-b-2 border-gray-300 focus:outline-none focus:border-indigo-500 text-center py-1 signature-input bill-field">
                                <label class="block text-sm font-semibold text-gray-600 mt-2">FIC, Reprography</label>
                            </div>
                        </div>
                    </div>

                    <!-- CHANGED: Note Section Added -->
                    <div class="mt-8 pt-4 border-t border-dashed">
                        <p class="text-xs text-gray-600 italic">
                            <span class="font-bold">Note:</span> The Charges may be credited under A/C 07-03-0202, Use of Reprography Facility.
                        </p>
                    </div>

                {% else %}
                    <p class="text-center text-gray-500 py-8">No items added to the bill yet.</p>
                {% endif %}
            </div>

            <div class="mt-8 flex justify-center gap-4 no-print fade-in" style="animation-delay: 0.3s;">
                <button onclick="window.print()"
                        class="bg-green-600 text-white font-bold py-2 px-6 rounded-md hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 transition">
                    Print Bill
                </button>
                <a href="/new"
                   class="bg-blue-600 text-white font-bold py-2 px-6 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition">
                    New Bill
                </a>
            </div>
        </div>
    </div>
    
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            // Logic for auto-saving bill fields
            const billFields = document.querySelectorAll('.bill-field');
            billFields.forEach(input => {
                input.addEventListener('change', function() {
                    const billId = this.getAttribute('data-bill-id');
                    const fieldName = this.getAttribute('data-field');
                    const value = this.value;

                    fetch('/update_bill', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            bill_id: billId,
                            field: fieldName,
                            value: value
                        })
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.status !== 'success') {
                            console.error('Failed to update field:', fieldName);
                        }
                    });
                });
            });

            const itemCodeMap = {{ item_codes|tojson }};
            const itemCodeSelect = document.getElementById('item_code');
            const itemNameInput = document.getElementById('item_name');
            const unitsInput = document.getElementById('units');
            const rateInput = document.getElementById('rate');
            const amountInput = document.getElementById('amount');

            function calculateAmount() {
                const units = parseFloat(unitsInput.value) || 0;
                const rate = parseFloat(rateInput.value) || 0;
                const amount = units * rate;
                amountInput.value = amount.toFixed(2);
            }

            if (itemCodeSelect) {
                itemCodeSelect.addEventListener('change', function() {
                    const selectedCode = this.value;

                    if (selectedCode === '0000') {
                        itemNameInput.value = '';
                        rateInput.value = '0.00';
                        unitsInput.value = '1';
                        
                        itemNameInput.readOnly = false;
                        itemNameInput.classList.remove('bg-gray-100', 'cursor-not-allowed');
                        itemNameInput.classList.add('bg-white');
                        itemNameInput.focus();
                    } else {
                        const itemData = itemCodeMap[selectedCode];
                        if (itemData) {
                            itemNameInput.value = itemData.name;
                            rateInput.value = itemData.rate.toFixed(2);
                        } else {
                            itemNameInput.value = '';
                            rateInput.value = '0.00';
                        }
                        
                        itemNameInput.readOnly = true;
                        itemNameInput.classList.add('bg-gray-100', 'cursor-not-allowed');
                        itemNameInput.classList.remove('bg-white');
                    }
                    
                    calculateAmount();
                });
            }

            if(unitsInput && rateInput && amountInput) {
                unitsInput.addEventListener('input', calculateAmount);
                rateInput.addEventListener('input', calculateAmount);
                calculateAmount();
            }
        });
    </script>
</body>
</html>
"""

# --- Flask Routes (Updated to use SQLAlchemy) ---

@app.route('/')
def index():
    """Renders the main page, creating a new bill if none exists."""
    db = get_db()

    # Fetch products
    products = db.query(Product).order_by(Product.item_code.asc()).all()
    db_item_codes = {p.item_code: {'name': p.item_name, 'rate': p.default_rate} for p in products}

    # Fetch the most recent bill
    current_bill = db.query(Bill).order_by(Bill.id.desc()).first()

    if not current_bill:
        return redirect(url_for('new_bill'))
    
    # Handle the bill_display_id (if empty, set it to the Bill ID)
    if not current_bill.bill_display_id:
        current_bill.bill_display_id = str(current_bill.id)
        db.commit()
        # Re-fetch the updated bill object
        current_bill = db.query(Bill).filter(Bill.id == current_bill.id).first()

    # Fetch bill items using the relationship, convert to dict for template compatibility
    items = [
        {'id': item.id, 'name': item.name, 'units': item.units, 'rate': item.rate, 'amount': item.amount}
        for item in current_bill.items
    ]
    
    # Convert SQLAlchemy model instance to dictionary for render_template_string
    bill_dict = {
        'id': current_bill.id,
        'bill_display_id': current_bill.bill_display_id,
        'bill_date': current_bill.bill_date,
        'recipient': current_bill.recipient,
        'prepared_by': current_bill.prepared_by,
        'checked_by': current_bill.checked_by,
        'fic_reprography': current_bill.fic_reprography,
    }
    
    total = sum(item['amount'] for item in items)
    return render_template_string(HTML_TEMPLATE, bill=bill_dict, items=items, total_amount=total, item_codes=db_item_codes)

@app.route('/add', methods=['POST'])
def add_item():
    """Adds a new item to the current bill."""
    try:
        item_name = request.form['item_name']
        units = int(request.form['units'])
        rate = float(request.form['rate'])
        bill_id = int(request.form['bill_id'])

        if not item_name or units <= 0 or rate < 0 or bill_id is None:
            return redirect(url_for('index'))
        
        amount = units * rate

        db = get_db()
        
        new_item = BillItem(
            name=item_name, 
            units=units, 
            rate=rate, 
            amount=amount, 
            bill_id=bill_id
        )
        db.add(new_item)
        db.commit()
        
    except (ValueError, KeyError, IntegrityError) as e:
        # IntegrityError catches foreign key violations (e.g., if bill_id doesn't exist)
        print(f"Error adding item: {e}")
        pass
        
    return redirect(url_for('index'))

@app.route('/new')
def new_bill():
    """Creates a new, empty bill and sets its display ID."""
    db = get_db()
    today_date = date.today().isoformat()

    new_bill = Bill(bill_date=today_date, bill_display_id='')
    db.add(new_bill)
    db.flush() # Forces INSERT to get the new primary key (id)
    
    new_bill.bill_display_id = str(new_bill.id)
    
    db.commit()
    return redirect(url_for('index'))

@app.route('/update_bill', methods=['POST'])
def update_bill():
    """Updates a specific field of a bill."""
    data = request.get_json()
    bill_id = data.get('bill_id')
    field = data.get('field')
    value = data.get('value')

    allowed_fields = ['bill_display_id', 'bill_date', 'recipient', 'prepared_by', 'checked_by', 'fic_reprography']
    if field not in allowed_fields:
        return jsonify({'status': 'error', 'message': 'Invalid field'}), 400

    if bill_id is None or value is None:
        return jsonify({'status': 'error', 'message': 'Missing data'}), 400

    db = get_db()
    try:
        # Find the bill to update
        bill = db.query(Bill).filter(Bill.id == bill_id).first()
        
        if bill:
            # Dynamically update the field
            setattr(bill, field, value)
            db.commit()
            return jsonify({'status': 'success'})
        else:
            return jsonify({'status': 'error', 'message': 'Bill not found'}), 404
            
    except Exception as e:
        db.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

# --- Main Execution ---
if __name__ == '__main__':
    init_db()
    app.run(debug=True)
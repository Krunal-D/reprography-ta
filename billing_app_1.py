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
DATABASE_URL = os.environ.get(
    "DATABASE_URL", 
    "sqlite:///billing.db"
)
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Model Definitions ---
class Bill(Base):
    __tablename__ = 'bills'
    id = Column(Integer, primary_key=True)
    bill_display_id = Column(Text, unique=True, index=True)
    bill_date = Column(Text, nullable=False)
    recipient = Column(Text)
    prepared_by = Column(Text)
    checked_by = Column(Text)
    fic_reprography = Column(Text)
    job_description = Column(Text)
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
    Base.metadata.create_all(bind=engine) 
    db = next(get_db())
    try:
        if db.query(Product).count() == 0:
            sample_products = [
                Product(item_code='0000', item_name='Custom Item', default_rate=0.00),
                Product(item_code='0001', item_name='A4 Plain Paper Ream', default_rate=350.00),
                Product(item_code='0002', item_name='Official Envelope (Pack of 100)', default_rate=150.00),
                Product(item_code='0003', item_name='Spiral Binding Service', default_rate=50.00),
                Product(item_code='0004', item_name='Color Printout (A4)', default_rate=10.00)
            ]
            db.add_all(sample_products)
            db.commit()
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
        @page { size: A5; margin: 0; }
        @media print {
            /* NEW: Center the bill on the page */
            body { 
                display: flex;
                justify-content: center;
                align-items: flex-start;
                background: white !important; 
                -webkit-print-color-adjust: exact; 
                print-color-adjust: exact;
            }
            .no-print { display: none !important; }
            .print-container { transform: scale(0.95); transform-origin: top center; width: 100%; height: 100%; }
            #bill-section { box-shadow: none !important; border: 1px solid #ccc !important; page-break-inside: avoid; }
            .header-logo-print { height: 3.5rem; margin-right: 1rem; }
            .signature-container-print { margin-top: 2rem !important; }
            .signature-grid-print { display: flex !important; justify-content: space-between !important; gap: 1.5rem !important; }
            .signature-grid-print > div { flex: 1; }
            .overflow-x-auto { overflow-x: visible !important; }
            .rate-column { display: none !important; }
            .print-only-tfoot { display: table-footer-group !important; }
        }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); } }
        .fade-in { animation: fadeIn 0.5s ease-out forwards; }
        .print-only-tfoot { display: none; }
        #admin-modal-overlay { transition: opacity 0.3s ease-in-out; }
        #admin-modal-content { transition: transform 0.3s ease-in-out; }
    </style>
</head>
<body class="bg-gray-100 text-gray-800 font-sans">
    <div class="print-container">
        <div class="container mx-auto p-4 md:p-8 max-w-4xl">
            <div class="bg-white rounded-lg shadow-md p-6 mb-8 no-print fade-in" style="animation-delay: 0.1s;">
                <div class="flex justify-between items-center mb-4 border-b pb-2">
                    <h2 class="text-2xl font-semibold">Add Billing Item</h2>
                    <button id="open-admin-modal" class="text-gray-400 hover:text-indigo-600 transition">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v3m0 0v3m0-3h3m-3 0H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                    </button>
                </div>
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
                        <input type="text" id="item_name" name="item_name" required readonly class="mt-1 block w-full px-3 py-2 bg-gray-100 border border-gray-300 rounded-md shadow-sm cursor-not-allowed">
                    </div>
                    <div>
                        <label for="units" class="block text-sm font-medium text-gray-600">Units</label>
                        <input type="number" id="units" name="units" required min="1" value="1" class="mt-1 block w-full px-3 py-2 bg-white border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500">
                    </div>
                    <div>
                        <label for="rate" class="block text-sm font-medium text-gray-600">Rate</label>
                        <input type="number" id="rate" name="rate" required min="0" step="0.01" value="0.00" class="mt-1 block w-full px-3 py-2 bg-white border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500">
                    </div>
                    <div class="md:col-span-1">
                        <label for="amount" class="block text-sm font-medium text-gray-600">Amount</label>
                        <input type="number" id="amount" name="amount" required readonly class="mt-1 block w-full px-3 py-2 bg-gray-100 border border-gray-300 rounded-md shadow-sm cursor-not-allowed">
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
                    <div class="mt-8 pt-4 border-t border-dashed">
                        <div class="flex items-center">
                            <label for="job_description" class="font-bold mr-2 text-gray-700">Job:</label>
                            <input type="text" id="job_description" placeholder="Enter job description or details..." value="{{ bill.job_description or '' }}" data-bill-id="{{ bill.id }}" data-field="job_description" class="w-full p-1 border-0 border-b-2 border-gray-200 focus:ring-0 focus:border-indigo-500 bill-field">
                        </div>
                    </div>
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
                <button onclick="window.print()" class="bg-green-600 text-white font-bold py-2 px-6 rounded-md hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 transition">
                    Print Bill
                </button>
                <a href="/new" class="bg-blue-600 text-white font-bold py-2 px-6 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition">
                    New Bill
                </a>
            </div>
        </div>
    </div>
    
    <div id="admin-modal" class="fixed inset-0 z-50 flex items-center justify-center hidden no-print">
        <div id="admin-modal-overlay" class="absolute inset-0 bg-black bg-opacity-50"></div>
        <div id="admin-modal-content" class="bg-white rounded-lg shadow-xl p-6 w-full max-w-2xl transform scale-95">
            <div class="flex justify-between items-center border-b pb-3 mb-4">
                <h3 class="text-2xl font-semibold">Manage Products</h3>
                <button id="close-admin-modal" class="text-gray-400 hover:text-red-600">&times;</button>
            </div>
            
            <div class="max-h-64 overflow-y-auto mb-4">
                <table class="min-w-full divide-y divide-gray-200">
                    <thead class="bg-gray-50">
                        <tr>
                            <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Code</th>
                            <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                            <th class="px-4 py-2 text-right text-xs font-medium text-gray-500 uppercase">Rate</th>
                            <th class="px-4 py-2 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
                        </tr>
                    </thead>
                    <tbody id="product-list" class="bg-white divide-y divide-gray-200">
                    </tbody>
                </table>
            </div>

            <form id="product-form" class="border-t pt-4">
                <h4 class="text-lg font-semibold mb-2" id="product-form-title">Add New Product</h4>
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                        <label for="product_item_code" class="block text-sm font-medium text-gray-700">Item Code</label>
                        <input type="text" id="product_item_code" name="item_code" required class="mt-1 block w-full border-gray-300 rounded-md shadow-sm">
                    </div>
                    <div>
                        <label for="product_item_name" class="block text-sm font-medium text-gray-700">Item Name</label>
                        <input type="text" id="product_item_name" name="item_name" required class="mt-1 block w-full border-gray-300 rounded-md shadow-sm">
                    </div>
                    <div>
                        <label for="product_default_rate" class="block text-sm font-medium text-gray-700">Default Rate</label>
                        <input type="number" id="product_default_rate" name="default_rate" step="0.01" required class="mt-1 block w-full border-gray-300 rounded-md shadow-sm">
                    </div>
                </div>
                <div class="flex justify-end mt-4">
                    <button type="button" id="cancel-edit-btn" class="hidden mr-2 px-4 py-2 bg-gray-200 text-gray-800 rounded-md hover:bg-gray-300">Cancel</button>
                    <button type="submit" class="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700">Save Product</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        document.addEventListener('DOMContentLoaded', function() {
            // --- Main Billing Page Logic ---
            const billFields = document.querySelectorAll('.bill-field');
            billFields.forEach(input => {
                input.addEventListener('change', function() {
                    const billId = this.getAttribute('data-bill-id');
                    const fieldName = this.getAttribute('data-field');
                    const value = this.value;
                    fetch('/update_bill', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ bill_id: billId, field: fieldName, value: value })
                    }).then(res => res.json()).then(data => {
                        if (data.status !== 'success') console.error('Failed to update field:', fieldName);
                    });
                });
            });

            let itemCodeMap = {{ item_codes|tojson }};
            const itemCodeSelect = document.getElementById('item_code');
            const itemNameInput = document.getElementById('item_name');
            const unitsInput = document.getElementById('units');
            const rateInput = document.getElementById('rate');
            const amountInput = document.getElementById('amount');

            function calculateAmount() {
                const units = parseFloat(unitsInput.value) || 0;
                const rate = parseFloat(rateInput.value) || 0;
                amountInput.value = (units * rate).toFixed(2);
            }

            if (itemCodeSelect) {
                itemCodeSelect.addEventListener('change', function() {
                    const selectedCode = this.value;
                    if (selectedCode === '0000') {
                        itemNameInput.value = ''; rateInput.value = '0.00'; unitsInput.value = '1';
                        itemNameInput.readOnly = false;
                        itemNameInput.classList.remove('bg-gray-100', 'cursor-not-allowed');
                        itemNameInput.classList.add('bg-white');
                        itemNameInput.focus();
                    } else {
                        const itemData = itemCodeMap[selectedCode];
                        itemNameInput.value = itemData ? itemData.name : '';
                        rateInput.value = itemData ? itemData.rate.toFixed(2) : '0.00';
                        itemNameInput.readOnly = true;
                        itemNameInput.classList.add('bg-gray-100', 'cursor-not-allowed');
                        itemNameInput.classList.remove('bg-white');
                    }
                    calculateAmount();
                });
            }
            if(unitsInput && rateInput) {
                unitsInput.addEventListener('input', calculateAmount);
                rateInput.addEventListener('input', calculateAmount);
            }

            // --- Admin Modal Logic ---
            const adminModal = document.getElementById('admin-modal');
            const openModalBtn = document.getElementById('open-admin-modal');
            const closeModalBtn = document.getElementById('close-admin-modal');
            const productList = document.getElementById('product-list');
            const productForm = document.getElementById('product-form');
            const productFormTitle = document.getElementById('product-form-title');
            const cancelEditBtn = document.getElementById('cancel-edit-btn');

            async function fetchProducts() {
                const response = await fetch('/api/products');
                const products = await response.json();
                renderProducts(products);
                
                itemCodeMap = {};
                products.forEach(p => {
                    itemCodeMap[p.item_code] = { name: p.item_name, rate: p.default_rate };
                });
                updateMainDropdown(products);
            }
            
            function renderProducts(products) {
                productList.innerHTML = '';
                products.forEach(p => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td class="px-4 py-2 text-sm">${p.item_code}</td>
                        <td class="px-4 py-2 text-sm">${p.item_name}</td>
                        <td class="px-4 py-2 text-sm text-right">₹${p.default_rate.toFixed(2)}</td>
                        <td class="px-4 py-2 text-sm text-right">
                            <button class="edit-btn text-indigo-600 hover:underline" data-code="${p.item_code}">Edit</button>
                            ${p.item_code !== '0000' ? `<button class="delete-btn text-red-600 hover:underline ml-2" data-code="${p.item_code}">Delete</button>` : ''}
                        </td>
                    `;
                    productList.appendChild(tr);
                });
            }

            function updateMainDropdown(products) {
                const currentVal = itemCodeSelect.value;
                itemCodeSelect.innerHTML = '<option value="" disabled selected>Select</option>';
                products.forEach(p => {
                    const option = document.createElement('option');
                    option.value = p.item_code;
                    option.textContent = p.item_code;
                    itemCodeSelect.appendChild(option);
                });
                itemCodeSelect.value = currentVal;
            }
            
            function resetProductForm() {
                productForm.reset();
                document.getElementById('product_item_code').readOnly = false;
                productFormTitle.textContent = 'Add New Product';
                cancelEditBtn.classList.add('hidden');
            }

            openModalBtn.addEventListener('click', () => { 
                adminModal.classList.remove('hidden');
                fetchProducts();
            });
            
            function closeAndReload() {
                adminModal.classList.add('hidden');
                window.location.reload();
            }

            closeModalBtn.addEventListener('click', closeAndReload);
            adminModal.querySelector('#admin-modal-overlay').addEventListener('click', closeAndReload);
            
            productForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const formData = new FormData(productForm);
                const code = formData.get('item_code');
                const isEditing = document.getElementById('product_item_code').readOnly;
                
                const url = isEditing ? `/api/products/${code}` : '/api/products';
                const method = isEditing ? 'PUT' : 'POST';

                const response = await fetch(url, {
                    method: method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(Object.fromEntries(formData))
                });
                
                if (response.ok) {
                    resetProductForm();
                    fetchProducts();
                } else {
                    const error = await response.json();
                    alert(`Error: ${error.message || 'Could not save product.'}`);
                }
            });

            productList.addEventListener('click', (e) => {
                const target = e.target;
                const code = target.dataset.code;

                if (target.classList.contains('edit-btn')) {
                    const row = target.closest('tr');
                    document.getElementById('product_item_code').value = code;
                    document.getElementById('product_item_code').readOnly = true;
                    document.getElementById('product_item_name').value = row.children[1].textContent;
                    document.getElementById('product_default_rate').value = parseFloat(row.children[2].textContent.replace('₹', ''));
                    productFormTitle.textContent = 'Edit Product';
                    cancelEditBtn.classList.remove('hidden');
                }
                
                if (target.classList.contains('delete-btn')) {
                    if (confirm(`Are you sure you want to delete item ${code}?`)) {
                        fetch(`/api/products/${code}`, { method: 'DELETE' }).then(res => {
                            if (res.ok) fetchProducts();
                            else alert('Error deleting product.');
                        });
                    }
                }
            });
            
            cancelEditBtn.addEventListener('click', resetProductForm);
        });
    </script>
</body>
</html>
"""

# --- Flask Routes ---

@app.route('/')
def index():
    db = next(get_db())
    products = db.query(Product).order_by(Product.item_code.asc()).all()
    db_item_codes = {p.item_code: {'name': p.item_name, 'rate': p.default_rate} for p in products}
    current_bill = db.query(Bill).order_by(Bill.id.desc()).first()
    if not current_bill:
        return redirect(url_for('new_bill'))
    if not current_bill.bill_display_id:
        current_bill.bill_display_id = str(current_bill.id)
        db.commit()
        current_bill = db.query(Bill).filter(Bill.id == current_bill.id).first()
    items = [{'id': i.id, 'name': i.name, 'units': i.units, 'rate': i.rate, 'amount': i.amount} for i in current_bill.items]
    bill_dict = {c.name: getattr(current_bill, c.name) for c in current_bill.__table__.columns}
    total = sum(item['amount'] for item in items)
    return render_template_string(HTML_TEMPLATE, bill=bill_dict, items=items, total_amount=total, item_codes=db_item_codes)

@app.route('/add', methods=['POST'])
def add_item():
    try:
        db = next(get_db())
        new_item = BillItem(
            name=request.form['item_name'], 
            units=int(request.form['units']), 
            rate=float(request.form['rate']), 
            amount=int(request.form['units']) * float(request.form['rate']), 
            bill_id=int(request.form['bill_id'])
        )
        db.add(new_item)
        db.commit()
    except (ValueError, KeyError, IntegrityError): pass
    return redirect(url_for('index'))

@app.route('/new')
def new_bill():
    db = next(get_db())
    new_bill = Bill(bill_date=date.today().isoformat(), bill_display_id='')
    db.add(new_bill)
    db.flush()
    new_bill.bill_display_id = str(new_bill.id)
    db.commit()
    return redirect(url_for('index'))

@app.route('/update_bill', methods=['POST'])
def update_bill():
    data, db = request.get_json(), next(get_db())
    allowed = ['bill_display_id', 'bill_date', 'recipient', 'prepared_by', 'checked_by', 'fic_reprography', 'job_description']
    if data.get('field') in allowed:
        bill = db.query(Bill).filter(Bill.id == data.get('bill_id')).first()
        if bill:
            setattr(bill, data.get('field'), data.get('value'))
            db.commit()
            return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

# --- API Routes for Product Management ---
@app.route('/api/products', methods=['GET'])
def get_products():
    db = next(get_db())
    products = db.query(Product).order_by(Product.item_code.asc()).all()
    return jsonify([{'item_code': p.item_code, 'item_name': p.item_name, 'default_rate': p.default_rate} for p in products])

@app.route('/api/products', methods=['POST'])
def create_product():
    data, db = request.get_json(), next(get_db())
    try:
        new_product = Product(
            item_code=data['item_code'],
            item_name=data['item_name'],
            default_rate=float(data['default_rate'])
        )
        db.add(new_product)
        db.commit()
        return jsonify({'status': 'success'}), 201
    except (IntegrityError, KeyError):
        db.rollback()
        return jsonify({'status': 'error', 'message': 'Invalid data or item code already exists.'}), 400

@app.route('/api/products/<string:item_code>', methods=['PUT'])
def update_product(item_code):
    data, db = request.get_json(), next(get_db())
    product = db.query(Product).filter(Product.item_code == item_code).first()
    if product:
        product.item_name = data.get('item_name', product.item_name)
        product.default_rate = float(data.get('default_rate', product.default_rate))
        db.commit()
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error', 'message': 'Product not found'}), 404

@app.route('/api/products/<string:item_code>', methods=['DELETE'])
def delete_product(item_code):
    if item_code == '0000':
        return jsonify({'status': 'error', 'message': 'Cannot delete the custom item.'}), 403
    db = next(get_db())
    product = db.query(Product).filter(Product.item_code == item_code).first()
    if product:
        db.delete(product)
        db.commit()
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error', 'message': 'Product not found'}), 404

# --- Main Execution ---
if __name__ == '__main__':
    init_db()
    app.run(debug=True)


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
# (Your original HTML_TEMPLATE remains here, UNCHANGED)
HTML_TEMPLATE = """
... (Your full HTML_TEMPLATE content is here) ...
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
# if __name__ == '__main__':
#     init_db()
#     app.run(debug=True) 
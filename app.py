from flask import Flask
from signalwire_swaig.core import SWAIG, SWAIGArgument, SWAIGArgumentItems
import random
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import psycopg2
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship

load_dotenv()

## POSTGRES CONFIGIGURATION ##
#PGUSER = os.getenv("PGUSER")
#PGPASSWORD = os.getenv("PGPASSWORD")
#PGHOST = os.getenv("PGHOST")
#PGPORT = os.getenv("PGPORT")
#PGDATABASE = os.getenv("PGDATABASE")
DB_CONNECTION_URL = os.getenv("DB_CONNECTION_URL")
if DB_CONNECTION_URL and DB_CONNECTION_URL.startswith('postgres://'):
    DB_CONNECTION_URL = DB_CONNECTION_URL.replace('postgres://', 'postgresql://', 1) # Replace postgres with postgresql for sqlalchemy
##

if not DB_CONNECTION_URL:
    raise ValueError("Missing DB_CONNECTION_URL environment variable")

app = Flask(__name__)
# Configure SQLAlchemy
#app.config['SQLALCHEMY_DATABASE_URI'] = f"postgresql://{PGUSER}:{PGPASSWORD}@{PGHOST}:{PGPORT}/{PGDATABASE}"
app.config['SQLALCHEMY_DATABASE_URI'] = DB_CONNECTION_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

swaig = SWAIG(app)

# Define models
class Flight(db.Model):
    __tablename__ = 'flights'
    
    id = db.Column(db.Integer, primary_key=True)
    record_locator = db.Column(db.String(6), unique=True, nullable=False)
    from_city = db.Column(db.String(3), nullable=False)  # Changed to 3 chars for IATA code
    to_city = db.Column(db.String(3), nullable=False)    # Changed to 3 chars for IATA code
    departure_date = db.Column(db.Date, nullable=False)
    return_date = db.Column(db.Date, nullable=True)
    aircraft_type = db.Column(db.String(50), nullable=False)
    passengers = relationship("Passenger", backref="flight", cascade="all, delete-orphan")

class Passenger(db.Model):
    __tablename__ = 'passengers'
    
    id = db.Column(db.Integer, primary_key=True)
    flight_id = db.Column(db.Integer, db.ForeignKey('flights.id'), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    contact_number = db.Column(db.String(20), nullable=False)
    seat_pref = db.Column(db.String(20), nullable=False)
    seat_number = db.Column(db.String(3), nullable=False)
    airfare_price = db.Column(db.String(10), nullable=False)

# Create tables
with app.app_context():
    # Check if tables exist before creating them
    inspector = db.inspect(db.engine)

    if not inspector.has_table('flights'):
        Flight.__table__.create(db.engine)
    
    if not inspector.has_table('passengers'):
        Passenger.__table__.create(db.engine)

def generate_record_locator():
    return ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=6))

def assign_seat(pref):
    """
    Assigns a seat based on passenger preference:
    - window: seats A or F (at the window)
    - aisle: seats C or D (on the aisle)
    - middle: seats B or E (between window and aisle)
    """
    row = random.randint(10, 45)
    if pref.lower() == "window":
        seat = f"{row}{random.choice(['A', 'F'])}"
        # A is left window, F is right window
    elif pref.lower() == "aisle":
        seat = f"{row}{random.choice(['C', 'D'])}"
        # C is left aisle, D is right aisle
    else:  # Default to middle if not specified or unknown preference
        seat = f"{row}{random.choice(['B', 'E'])}"
        # B is left middle, E is right middle
    
    return seat

def random_aircraft():
    return random.choice([
        "Boeing 737", "Airbus A320", "Boeing 787 Dreamliner", "Airbus A350", "Boeing 777"
    ])

# Add IATA validation function
def validate_iata_code(code):
    """Validates if a string is a proper IATA airport code."""
    if not code or not isinstance(code, str):
        return False
    # IATA codes are 3 alphabetic characters
    return len(code) == 3 and code.isalpha() and code.upper() == code

# Generate a price for the flight based on seat preference and if there i sa return date
def generate_price(seat_pref, return_date=None):
    total_cost = 0
    base_price = 200

    if return_date:
        total_cost = base_price * 2
    else:
        total_cost = base_price

    if seat_pref == "window":
        total_cost = total_cost * 1.2
    elif seat_pref == "aisle":
        total_cost = total_cost * 1.5
    else:
        total_cost = total_cost * 1.1
    
    return total_cost

@swaig.endpoint("Book a flight", 
    from_city=SWAIGArgument("string", "Origin airport IATA code (3 letters)", required=True),
    to_city=SWAIGArgument("string", "Destination airport IATA code (3 letters)", required=True),
    departure_date=SWAIGArgument("string", "Departure date in YYYY-MM-DD", required=True),
    return_date=SWAIGArgument("string", "Return date in YYYY-MM-DD", required=True),
    first_name=SWAIGArgument("string", "First name of passenger", required=True),
    last_name=SWAIGArgument("string", "Last name of passenger", required=True),
    seat_pref=SWAIGArgument("string", "Seat preference (window, aisle, or middle)", required=True),
    contact_number=SWAIGArgument("string", "Contact Phone Number (10 digits)", required=True))
def book_flight(from_city, to_city, departure_date, return_date, first_name, last_name, seat_pref, contact_number, meta_data_token=None, meta_data=None):
    # Customer Full Name
    full_name = f"{first_name} {last_name}"

    # Customer Contact Number
    # TODO: Validate contact number to make sure it is in the right format
    contact_number = contact_number

    # Validate IATA codes
    from_city = from_city.upper()
    to_city = to_city.upper()
    
    if not validate_iata_code(from_city):
        return f"Error: '{from_city}' is not a valid IATA airport code. Please use a 3-letter code like 'JFK' or 'LAX'.", {}
    
    if not validate_iata_code(to_city):
        return f"Error: '{to_city}' is not a valid IATA airport code. Please use a 3-letter code like 'JFK' or 'LAX'.", {}
    
    # Validate dates
    dep = datetime.strptime(departure_date, "%Y-%m-%d")
    if dep < datetime.now() + timedelta(hours=24):
        return "Error: Flights must be booked at least 24 hours in advance.", {}

    # Validate passenger data and seat preferences
    valid_preferences = ["window", "aisle", "middle"]
    if seat_pref.lower() not in valid_preferences:
        seat_pref = "middle"  # Default to middle if not specified, or invalid
    else:  
        seat_pref = seat_pref.lower()

    # Remaining booking logic
    locator = generate_record_locator()
    aircraft = random_aircraft()

    new_flight = Flight(
        record_locator=locator,
        from_city=from_city,
        to_city=to_city,
        departure_date=departure_date,
        return_date=return_date,
        aircraft_type=aircraft
    )
    db.session.add(new_flight)
    db.session.flush()  # To get the flight ID

    # Create a confirmation message with seat assignments
    confirmation = [f"Flight booked successfully! Record locator: {locator}"]
    confirmation.append(f"Route: {from_city} → {to_city}")
    confirmation.append(f"Departure: {departure_date}")
    if return_date:
        confirmation.append(f"Return: {return_date}")
    confirmation.append(f"Aircraft: {aircraft}")
    confirmation.append("\nPassenger Information:")

    seat = assign_seat(seat_pref)
    price = generate_price(seat_pref, return_date=return_date)
    confirmation.append(f"Total price: ${price:.2f}")

    new_passenger = Passenger(
        flight_id=new_flight.id,
        full_name=full_name,
        contact_number=contact_number,
        seat_pref=seat_pref,
        seat_number=seat,
        airfare_price=price
    )
    
 

    db.session.add(new_passenger)
    confirmation.append(f"- {full_name}: {seat_pref.capitalize()} seat {seat}")

    db.session.commit()
    print (confirmation)
    return "\n".join(confirmation), {}

@swaig.endpoint("Lookup a flight", 
    record_locator=SWAIGArgument("string", "Record locator for the booking"))
def lookup_flight(record_locator, meta_data_token=None, meta_data=None):
    flight = Flight.query.filter_by(record_locator=record_locator.upper()).first()
    if not flight:
        return "No flight found with that record locator.", {}
    
    # Create more detailed passenger information with formatted seat info
    passenger_data = []
    passenger_data.append({
        "name": flight.passengers[0].full_name,
        "contact": flight.passengers[0].contact_number,
        "seat_preference": flight.passengers[0].seat_pref,
        "assigned_seat": flight.passengers[0].seat_number,
        "seat_type": f"{flight.passengers[0].seat_pref.capitalize()} seat ({flight.passengers[0].seat_number})"
    })
    
    # Format return information in a more readable way
    flight_info = {
        "record_locator": flight.record_locator,
        "route": f"{flight.from_city} → {flight.to_city}",
        "departure_date": str(flight.departure_date),
        "return_date": str(flight.return_date) if flight.return_date else "One-way flight",
        "aircraft": flight.aircraft_type,
        "passengers": passenger_data
    }
    
    return str(flight_info), {}

@swaig.endpoint("Change flight details", 
    record_locator=SWAIGArgument("string", "Record locator for the booking"),
    new_departure_date=SWAIGArgument("string", "New departure date", required=False),
    new_return_date=SWAIGArgument("string", "New return date", required=False),
    new_from_city=SWAIGArgument("string", "New origin airport IATA code", required=False),
    new_to_city=SWAIGArgument("string", "New destination airport IATA code", required=False))
def change_flight(record_locator, new_departure_date=None, new_return_date=None, new_from_city=None, new_to_city=None, meta_data_token=None, meta_data=None):
    flight = Flight.query.filter_by(record_locator=record_locator.upper()).first()
    if not flight:
        return "Booking not found.", {}
    
    if new_departure_date:
        flight.departure_date = new_departure_date
    if new_return_date:
        flight.return_date = new_return_date
    if new_from_city:
        new_from_city = new_from_city.upper()
        if not validate_iata_code(new_from_city):
            return f"Error: '{new_from_city}' is not a valid IATA airport code. Please use a 3-letter code like 'JFK' or 'LAX'.", {}
        flight.from_city = new_from_city
    if new_to_city:
        new_to_city = new_to_city.upper()
        if not validate_iata_code(new_to_city):
            return f"Error: '{new_to_city}' is not a valid IATA airport code. Please use a 3-letter code like 'JFK' or 'LAX'.", {}
        flight.to_city = new_to_city
    
    db.session.commit()
    return "Flight updated successfully.", {}

@swaig.endpoint("Cancel a flight", 
    record_locator=SWAIGArgument("string", "Record locator to cancel"))
def cancel_flight(record_locator, meta_data_token=None, meta_data=None):
    flight = Flight.query.filter_by(record_locator=record_locator.upper()).first()
    if flight:
        db.session.delete(flight)  # This will cascade delete passengers too
        db.session.commit()
    return "Flight canceled successfully.", {}

if __name__ == '__main__':
    app.run(port=5000)
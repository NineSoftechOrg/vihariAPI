from flask import Flask, jsonify, request;
from flask_cors import CORS, cross_origin
from dotenv import load_dotenv
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from bson.objectid import ObjectId
from bson import json_util
import json
import os
import razorpay
import certifi
import googlemaps
import jwt
from functools import wraps
import datetime
import random
import re
from flask_caching import Cache
ca = certifi.where()


gmaps = googlemaps.Client(key='AIzaSyAL9K2tfUIeuX0SkO2EZ4Ig55gbtPeZs-c')




load_dotenv()

app = Flask(__name__)
SECRET_KEY = os.environ.get('SECRET_KEY') or 'bamsi'

app.config['SECRET_KEY'] = SECRET_KEY


app.config['CACHE_TYPE'] = os.environ.get('CACHE_TYPE')
app.config['CACHE_REDIS_HOST'] = os.environ.get('CACHE_REDIS_HOST')
app.config['CACHE_REDIS_PORT'] = os.environ.get('CACHE_REDIS_PORT')
app.config['CACHE_REDIS_DB'] = os.environ.get('CACHE_REDIS_DB')
app.config['CACHE_REDIS_URL'] = os.environ.get('CACHE_REDIS_URL')
app.config['CACHE_DEFAULT_TIMEOUT'] = os.environ.get('CACHE_DEFAULT_TIMEOUT')




client = MongoClient("mongodb+srv://bamsi:Alcuduur40@cluster0.vtlehsn.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0", tlsCAFile=ca)

db = client["vihari"]
CORS(app, resources={r"/*": {"origins": "*"}})



def getCurrentUser(id):
    admin = db["Admins"].find_one({"_id": ObjectId(id)})
    zoneAdmin = db['ZoneAdmins'].find_one({"_id": ObjectId(id)})
    driver = db['Driver'].find_one({"_id": ObjectId(id)})
    if admin:
        return admin['_id']
    elif zoneAdmin:
        return zoneAdmin['_id']
    elif driver:
        return driver['_id']


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if "Authorization" in request.headers:
            token = request.headers["Authorization"].split(" ")[1]
        if not token:
            return {
                "message": "Authentication Token is missing!",
                "data": None,
                "error": "Unauthorized"
            }, 401
        try:
            data=jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
            current_user= getCurrentUser(data["user_id"])
            # print(current_user)
            if current_user is None:
                return {
                "message": "Invalid Authentication token!",
                "data": None,
                "error": "Unauthorized"
            }, 401
            
        except Exception as e:
            return {
                "message": "Something went wrong",
                "data": None,
                "error": str(e)
            }, 500

        return f(current_user, *args, **kwargs)

    return decorated




@app.route('/')
def start():
    # print(currentUser)
    return "vihari api working..."


@app.route('/order', methods=["POST"])
def order():
    incoming_msg = request.get_json();

    razor = razorpay.Client(auth=("rzp_live_nma9bpaQRoARQg", "re38c3NxNAoGlfKs4aDPJPq8"))

    options = {
        'amount': incoming_msg['amount'] * 100,
        'currency': 'INR',
        'receipt': incoming_msg['firstname'] + "937932",
        'payment_capture': 1
    }

    response = razor.order.create(data=options)

    return response


@app.route('/createZone', methods=["POST"])
@token_required
def zone(currentUser):
    incoming_msg = request.get_json();
    zone = db['Zone']
    admin = db["Admins"]
    zone_check = zone.find_one({"zone_name": incoming_msg["zoneName"].upper()})
    
    if zone_check:
        return "already zone created", 404
    else:
        zone_dict = {
            "zone_name": incoming_msg['zoneName'].upper(),
            "added_by": admin.find_one({"_id": ObjectId(currentUser)})["role"],
            "geofence_radius": incoming_msg['geofence'],
            "price_matrix": [],
            "total_vehicles": [],
            'hourly_price': [],
            'hourly_price_round':[],
            "total_drivers": "",
            "status": "active"
        }

        zone.insert_one(zone_dict)
        return "zone created successfully", 200
    
    
    

@app.route('/setPriceZone', methods=["POST"])
@token_required
def pricing(currentUser):
    incoming_msg = request.get_json();
    zone = db['Zone'];
    vehicleType = incoming_msg['zoneName']['vehicleType'] if incoming_msg['trip'] == 'oneWay' else incoming_msg['vehicleType']
    # print(vehicleType)
    if incoming_msg['trip'] == "oneWay":
        up = zone.update_one({
            'zone_name': incoming_msg['zoneName']['zoneName']
        }, {
            "$set": {
                vehicleType : {
                    "price_per_km": incoming_msg['zoneName']['pricePerKm'], 
                    "hourly_price": incoming_msg['zoneName']['hourlyPrice']
                    
                }
                
            }
        })
    else:
        up = zone.update_one({
            'zone_name': incoming_msg['zoneName']['zoneName']
        }, {
            "$set": {
                vehicleType + "_round": {
                    "price_perkm_round": incoming_msg['priceroundTrip'],
                    "hourly_price_round": incoming_msg['hourlyPrice']
                }
            }
            
        })
    
    return "got price zone"



@app.route('/setBooking', methods=["POST"])
def setBooking():
        incoming_msg = request.get_json()['Body'];
        customer = db['Customer'].find_one({"_id": ObjectId(incoming_msg['user_id'])})
        bookings = db['Bookings']
        vehicles = db['Vehicles']
        zone = db["Zone"].find_one({'zone_name': incoming_msg['from'].upper()})
        capacity = vehicles.find_one({"vehicle_type": incoming_msg['car_model'], "zone_id": zone['_id']})
        
        
        carZone = db['Zone'].find_one({"_id": capacity['zone_id']})
        
        payload = {
            "orginZone": incoming_msg['from'],
            "to": incoming_msg['to'],
            "duration": incoming_msg['duration'],
            "distance": incoming_msg['distance'],
            "paymentId": incoming_msg['paymentId'] if incoming_msg['payment_type'] != "COD" else "",
            "total_trip_price": incoming_msg['price'],
            "trip_type": incoming_msg['tripType'],
            'trip_start_datetime': incoming_msg['time'],
            'trip_end_datetime': incoming_msg['trip_end_datetime'] if incoming_msg['tripType'] == "roundTrip" else "",
            'return_date': incoming_msg['returningDate'] if incoming_msg['tripType'] == "roundTrip" else "",
            'car_capacity': capacity['capacity'],
            'travel_date': incoming_msg['travel_date'],
            'car_type': incoming_msg['car_model'],
            'car_zone': carZone['zone_name'],
            'car_info': '',
            'car_registration_number': capacity['registration_number'],
            'booking_price': '',
            'payment_status': 'Paid' if incoming_msg['payment_type'] != "COD" else "PENDING",
            'payment_type': incoming_msg['payment_type'],
            'user_id': customer['_id'],
            'extra_payment_details': '',
            'pickup_location': incoming_msg['pickup'],
            'status': 'Booked'

        }
        
        
        bookings.insert_one(payload)
        j = list(bookings.find())[-1]
        # print(j['_id'])
        # payload['bookingId'] = str(j['_id'])

        user = db["Customer"].update_one({
            "_id": ObjectId(incoming_msg['user_id']),
        } , {
            '$push': {
                "booking_history": payload
            }
        }
        
        )
        
        return {
            "bookingId":str(j['_id'])
        }


@app.route('/getBookings')
@token_required
def getBookings(current):
    bookins = db['Bookings']
    all = list(bookins.find())
    return json.loads(json_util.dumps(all))

@app.route('/getBooking', methods=['POST'])
@token_required
def getBooking(current):
    incoming_msg = request.get_json()
    booking = db['Bookings'].find_one({"_id": ObjectId(incoming_msg['bookingId'])})
    if booking:
        return json.loads(json_util.dumps(booking))
    else:
        return "Not found that booking"

@app.route('/getZones')
@token_required
def getzones(currentUser):
    zones = db['Zone']
    
    zone = zones.find()
    zone_list = list(zone)
    return json.loads(json_util.dumps(zone_list))


@app.route('/getVendors')
@token_required
def getvendors(current):
    vendors = db['Vendors']
    
    vendor = vendors.find()
    vendor_list = list(vendor)
    return json.loads(json_util.dumps(vendor_list))


@app.route('/getVehicles')
@token_required
def getVehicles(current):
    vehicles = db['Vehicles']
    
    vehicle = vehicles.find()
    vehicles_list = list(vehicle)
    
    return json.loads(json_util.dumps(vehicles_list))


@app.route('/getUsers')
@token_required
def getUsers(current):
    users = db['Customer']
    
    user = users.find()
    users_list = list(user)
    
    return json.loads(json_util.dumps(users_list))

@app.route('/getUser', methods=["POST"])
def getUser():
    incoming_msg = request.get_json()
    users = db['Customer']
    
    user = users.find_one({"_id": ObjectId(incoming_msg['userId'])})
    users_list = user

    return users_list

@app.route('/getAdmins', methods=['GET'])
@token_required
def getAdmins(currentUser):
  
    admins = db['Admins'].find_one({"_id": ObjectId(currentUser)})
    zoneAdmins = db['ZoneAdmins'].find_one({"_id": ObjectId(currentUser)})
    driver = db['Driver'].find_one({"_id": ObjectId(currentUser)})
    if admins:
        return json.loads(json_util.dumps(admins))
    elif zoneAdmins:
        return json.loads(json_util.dumps(zoneAdmins))
    elif driver:
        return json.loads(json_util.dumps(driver))
    
@app.route('/updateAdmins', methods=['POST'])
@token_required
def updateAdmins(currentUser):
    incoming_msg = request.get_json()
    updateType = incoming_msg['type'][0]
    whereToUpdate = incoming_msg['type'][1]
    if updateType == 'Update':
        updateData = incoming_msg['data']
        db[whereToUpdate].update_one({"_id": ObjectId(incoming_msg['user_id'])}, {
            "$set": {
                **updateData
            }
        })
        return "Update successfully"
    elif updateType == 'Delete':
        db[whereToUpdate].delete_one({"_id": ObjectId(incoming_msg['user_id'])})
        return "Deleted Successfully"
    


@app.route('/getZoneAdmins')
@token_required
def getZoneAdmins(current):
    zoneAdmins = db['ZoneAdmins']
    
    zoneAdmin = zoneAdmins.find()
    zoneadmin_list = list(zoneAdmin)
    
    return json.loads(json_util.dumps(zoneadmin_list))

@app.route('/trips')
@token_required
def trips(current):
    bookings = db['Bookings']
    vehicles = db["Vehicles"]
    zone = db["Zone"]
    driver = db['Driver']
    all = list(bookings.find())
    f = []
    for i in all:
        zones = i['orginZone']
        vehicle_type = i['car_type']
        
        f.append(
            {
               "orderId": i["_id"],
               "originZone": i['orginZone'],
               "destination": i['to'],
               "tripType": i['trip_type'],
               "payment_status": i['payment_status'],
               "vehicle": list(vehicles.find({"vehicle_type": vehicle_type, "status": "active", "zone_id": zone.find_one({"zone_name": zones.upper()})['_id']})),
               "Driver":list(driver.find({"status": "active", "zone.zone_name": zones.upper()})),
               "status": i['status'],
               "car_type": i['car_type'],
               "travel_date": i['travel_date']
            }
        )
    # print(f)
    return json.loads(json_util.dumps(f))
    

@app.route('/updateDriverStatus')
@token_required
def updateDriverStatus(current):
    driver = db['Driver'].find_one({"_id": ObjectId(current)})
    if driver:
        if driver['status'] == 'inactive':
            db['Driver'].update_one({"_id": ObjectId(current)}, {
                "$set": {
                    "status": "active"
                }
            })
            return "Driver got active mode"
        elif driver['status'] == 'active':
            db['Driver'].update_one({"_id": ObjectId(current)}, {
                "$set": {
                    "status": "inactive"
                }
            })
            return "Driver got inactive mode"
    return "No driver found"


@app.route('/getDrivers')
@token_required
def getDrivers(current):
    drivers = db['Driver']
    
    driver = drivers.find()
    driver_list = list(driver)
    # for items in zone:
    #     zone_dict = {
    #         "zone_name": items["zone_name"],
    #         "geofence_radius": items["geofence_radius"],
    #         "price_matrix": items["price_matrix"],
    #         "total_vehicles": items["total_vehicles"],
    #         "total_drivers": items["total_drivers"]
    #     }
    # zone_list.append(zone_dict)
    
    
    return json.loads(json_util.dumps(driver_list))


@app.route('/startTrip', methods=["POST"])
@token_required
def startTrip(current):
    incoming_msg = request.get_json()
    driver = db['Driver']
    cartype = db['Bookings'].find_one({"_id": ObjectId(incoming_msg['bookingId'])})
    vehicle = db['Vehicles']
    availabe_vehicle = vehicle.find_one({ "vehicle_type": cartype['car_type'], "vehicle_name": incoming_msg['vehicleName'], "brand": incoming_msg['brand'], "status":"active"})
    available_driver = driver.find_one({"_id": ObjectId(incoming_msg['driver_id']), "status": "active"})
    payload = {
            "bookingId": ObjectId(incoming_msg["bookingId"]),
            "travel_Date": incoming_msg['travelDate'],
            "trip_status": "trip confirmed"
        }
    try:
        if availabe_vehicle and available_driver:
            vehicle.update_one({
                "vehicle_type": cartype['car_type'], "vehicle_name": incoming_msg['vehicleName'], "brand": incoming_msg['brand'], "status":"active"
            }, {
                '$set': {
                    "status":"assigned",
                    "bookingId": ObjectId(incoming_msg['bookingId'])
                }
            })
            driver.update_one({
            "_id": ObjectId(incoming_msg['driver_id']), "status": "active"
        }, {"$set": {
            "status": "assigned",
        }, 
            "$push": {
                "trips": payload,
            }
        })
            db['Customer'].update_one({'booking_history._id': ObjectId(incoming_msg['bookingId'])}, {
            "$set": {
                "booking_history.$.status": "trip confirmed"
            }
        })
            db['Bookings'].update_one({
                "_id": ObjectId(incoming_msg['bookingId'])
            }, {
                "$set": {
                    "status": "trip confirmed"
                }

            })
        else:
            raise e

    except Exception as e:
        return "couldn't assign a trip to a vehicle and a driver", 400
    
   
    

    
    
    return "Trip confirmed and assigned to a driver"




@app.route('/createDriver', methods=["POST"])
@token_required
def createDriver(currentUser):
    incoming_msg = request.get_json()["Body"];
    drivers = db["Driver"]
    zone = db["Zone"]
    zone = db["Zone"].find_one({"zone_name": incoming_msg["zone"]})
    driver_check = drivers.find_one({"mobile": incoming_msg['mobile']})
    customer_check = db['Customer'].find_one({"mobile": incoming_msg['mobile']})
    vendor_check = db['Vendors'].find_one({"mobile": incoming_msg['mobile']})
    if "Authorization" in request.headers:
        token = request.headers["Authorization"].split(" ")[1]
        
    if driver_check or customer_check or vendor_check:
        return "this number already used", 404
    
    else:
        driver_dict = {
            "firstname": incoming_msg["firstName"],
            "lastname": incoming_msg["lastName"],
            "mobile": incoming_msg["mobile"],
            "alt_mobile": incoming_msg["altNumber"],
            "email": incoming_msg["email"],
            "zone": zone,
            "license_number":incoming_msg["licenseNumber"],
            "driving_license":incoming_msg["drivingPhoto"],
            "id_proof_front_url": incoming_msg["imgUrl"],
            "address_proof_url": incoming_msg["addressProof"],
            "pan_card": incoming_msg["pan"],
            "status": "active",
            "trips": []

        }
        drivers.insert_one(driver_dict)

        return "Driver created successfully"

@app.route('/createAdmin')
def createAdmin():
    # incoming_msg = request.get_json();
    
    admin = db['Admins']
    zones = db["Zone"]
    zoneAdmin = zones.find_one({"zone_admin.name": "Bamsi"})
    admin_dict = {
        "firstname": "Admin",
        "lastName": "|Admin",
        "contact": "+918106666295",
        "email": "",
        "license_number": "",
        "role": 'admin'
    }
    admin.insert_one(admin_dict)
    # print(zoneAdmin)
    return "working..."


@app.route('/createCustomer', methods=["POST"])
def createCustomer():
    incoming_msg = request.get_json()
    customer = db['Customer']
    drivers = db['Driver']
    email = customer.find_one({"email": incoming_msg['email']})
    driver_check = drivers.find_one({"mobile": incoming_msg['phoneNumber']})
    customer_check = db['Customer'].find_one({"mobile": incoming_msg['phoneNumber']})
    vendor_check = db['Vendors'].find_one({"mobile": incoming_msg['phoneNumber']})
    number = random.randint(1000,9999)
    if driver_check or customer_check or vendor_check or email:
        return "this number already used or email", 404

    else:
        customer_dict = {
            "firstname": incoming_msg['firstName'],
            "lastname": incoming_msg['lastName'],
            "mobile": incoming_msg["phoneNumber"],
            "email": incoming_msg['email'],
            "location": {
                "lat": '',
                "long": ''
            },
            "search_history": [],
            "booking_history": [],
            "total_payments": "",
            "pending_payments": "",
            "feedback": [],
            "status": "",
            "profile_url": "",
            'role': "user",
            "otp": number
        }

        customer.insert_one(customer_dict)
        
    # print(incoming_msg)
    return "working...."

@app.route('/checkCustomer', methods=["POST"])
def checkCustomer():
    incoming_msg = request.get_json()
    customers = db['Customer']
    admin = db['Admins']
    zoneAdmin = db['ZoneAdmins']
    vendor = db['Vendors']
    onlyDriver = db['Driver'].find_one({"mobile": incoming_msg["phoneNumber"]})
    customer = customers.find_one({"mobile": incoming_msg["phoneNumber"]})
    onlyAdmin = admin.find_one({"contact": incoming_msg['phoneNumber']})
    onlyZoneAdmin = zoneAdmin.find_one({"mobile": incoming_msg['phoneNumber']})
    onlyVendors = vendor.find_one({"mobile": incoming_msg['phoneNumber']})

    
    

    if customer:
        data = {
        "firstname": customer['firstname'],
        "lastname": customer['lastname'],
        "email": customer['email'],
        "mobile": customer['mobile'],
        "role": customer['role'],
        "id": customer['_id']
    }   
        return json.loads(json_util.dumps(data))
    elif onlyAdmin:
        tokenAdmin = jwt.encode({'user_id' : str(onlyAdmin['_id']), 'exp' : datetime.datetime.utcnow() + datetime.timedelta(hours=24)}, app.config['SECRET_KEY'], "HS256")
        data = {
            "firstname": onlyAdmin['firstname'],
            "lastname": onlyAdmin['lastname'],
            "email": onlyAdmin['email'],
            "mobile": onlyAdmin['contact'],
            "role": onlyAdmin['role'],
            "id": onlyAdmin['_id'],
            "token": tokenAdmin
        }
        admin.update_one(onlyAdmin, {
            "$set": {
                "token": tokenAdmin
            }
        })
        # print(onlyAdmin['_id'])
        return json.loads(json_util.dumps(data))
    elif onlyZoneAdmin:
        zoneadminToken = jwt.encode({'user_id' : str(onlyZoneAdmin['_id']), 'exp' : datetime.datetime.utcnow() + datetime.timedelta(hours=24)}, app.config['SECRET_KEY'], "HS256")
        data = {
        "firstname": onlyZoneAdmin['firstname'],
        "lastname": onlyZoneAdmin['lastname'],
        "email": onlyZoneAdmin['email'],
        "mobile": onlyZoneAdmin['mobile'],
        "role": onlyZoneAdmin['role'],
        "id": onlyZoneAdmin['_id'],
        "token": zoneadminToken
        }
        zoneAdmin.update_one(onlyZoneAdmin, {
            "$set": {
                "token": zoneadminToken
            }
        })
        return json.loads(json_util.dumps(data))
    elif onlyVendors:
        data = {
        "firstname": onlyVendors['firstname'],
        "lastname": onlyVendors['lastname'],
        "email": onlyVendors['email'],
        "mobile": onlyVendors['mobile'],
        "role": onlyVendors['role'],
        "id": onlyVendors['_id']
        } 
        return json.loads(json_util.dumps(data))
    elif onlyDriver:
        driverToken = jwt.encode({'user_id' : str(onlyDriver['_id']), 'exp' : datetime.datetime.utcnow() + datetime.timedelta(hours=24)}, app.config['SECRET_KEY'], "HS256")
        db['Driver'].update_one(onlyDriver, {
            "$set": {
                "token": driverToken
                # "token": jwt({"user_id": str(onlyDriver["_id"])}, "driver", )
            }
        })
        data = {
        "firstname": onlyDriver['firstname'],
        "lastname": onlyDriver['lastname'],
        "email": onlyDriver['email'],
        "mobile": onlyDriver['mobile'],
        "id": onlyDriver['_id'],
        "token": driverToken
        } 
        return json.loads(json_util.dumps({
            "data": onlyDriver,
            "token": driverToken
        }))
    else:
        return "You are not registered, please register first", 400




@app.route('/createVendor', methods=["POST"])
@token_required
def createVendor(current):
    incoming_msg = request.get_json()["Body"];
    vendors = db['Vendors']
    zone = db["Zone"].find_one({"zone_name": incoming_msg["zone"]})
    drivers = db['Driver']
    driver_check = drivers.find_one({"mobile": incoming_msg['mobile']})
    customer_check = db['Customer'].find_one({"mobile": incoming_msg['mobile']})
    vendor_check = db['Vendors'].find_one({"mobile": incoming_msg['mobile']})
    if driver_check or customer_check or vendor_check:
        return "this number already used", 404

    else:
        vendors_dict = {
            "zone_id": zone['_id'],
            "firstname": incoming_msg["firstName"],
            "lastname": incoming_msg["lastName"],
            "mobile": incoming_msg["mobile"],
            "alt_mobile": incoming_msg["altNumber"],
            "email": incoming_msg["email"],
            "license_number": incoming_msg["licenseNumber"],
            "driving_license_front_url": incoming_msg["drivingPhoto"],
            "driving_license_back_url": "",
            "address_proof_url": incoming_msg["imgUrl"],
            "id_proof_front_url" :"",
            "id_proof_back_url": "",
            "profile_url": incoming_msg["profilePic"],
            "pan_card": "",
            "role": "vendor"
            
        }

        vendors.insert_one(vendors_dict)
        # print(incoming_msg)
        return "New Vendor created Successfully"

@app.route('/createZoneAdmin', methods=["POST"])
@token_required
def createZoneAdmin(current):
    incoming_msg = request.get_json()["Body"];
    zone_admins = db['ZoneAdmins']
    zoneName = incoming_msg['zone'].upper()
    zone = db["Zone"].find_one({"zone_name": zoneName})
    drivers = db['Driver']
    driver_check = drivers.find_one({"mobile": incoming_msg['mobile']})
    customer_check = db['Customer'].find_one({"mobile": incoming_msg['mobile']})
    vendor_check = db['Vendors'].find_one({"mobile": incoming_msg['mobile']})
    if driver_check or customer_check or vendor_check:
        return "this number already used", 404
    
    else:
        vendors_dict = {
            "zone_id": zone['_id'],
            "firstname": incoming_msg["firstName"],
            "lastname": incoming_msg["lastName"],
            "mobile": incoming_msg["mobile"],
            "alt_mobile": incoming_msg["altNumber"],
            "email": incoming_msg["email"],
            "license_number": incoming_msg["licenseNumber"],
            "driving_license_front_url": incoming_msg["drivingPhoto"],
            "driving_license_back_url": "",
            "address_proof_url": incoming_msg["imgUrl"],
            "id_proof_front_url" :"",
            "id_proof_back_url": "",
            "profile_url": incoming_msg["profilePic"],
            "pan_card": "",
            "role": "zoneAdmin"
            
        }

        zone_admins.insert_one(vendors_dict)
        # print(incoming_msg)
        return "ZoneAdmin got greated successfully"

@app.route('/createVehicle', methods=["POST"])
@token_required
def createVehicle(current):
    incoming_msg = request.get_json()["Body"];
    vehicles = db['Vehicles']
    zone = db["Zone"].find_one({"_id": ObjectId(incoming_msg["zone"])})
    checkRegisterNumber = vehicles.find_one({"registration_number": incoming_msg["registerNumber"]})
    vehicle_dict = {
        "zone_id": zone['_id'],
        "vehicle_name": incoming_msg["vehicleName"],
        "vehicle_type": incoming_msg["vehicleType"],
        "brand": incoming_msg["brand"],
        "capacity": incoming_msg["capacity"],
        "mileage": incoming_msg["mileage"],
        'zone': zone,
        "vehicle_owner": incoming_msg["ownerType"],
        "added_by" :incoming_msg["addedBy"],
        "registration_number":incoming_msg["registerNumber"],
        "vehicle_calender_availability": "",
        "status": "active",
        "fuel_type": incoming_msg['fuelType'],
        "rc_certificate": incoming_msg['rcCertificateUrl'],
        "premit_certificate": incoming_msg["permitCertificateUrl"],
        "fitness_certificate": incoming_msg["fitnessCertificateUrl"],
        "insurance_certificate": incoming_msg["insuranceCertificateUrl"],
        "pollution_certificate": incoming_msg["pollutionCertificateUrl"]
        
    }

    if checkRegisterNumber:
        return "This registration Number already there", 400
    

    vehicles.insert_one(vehicle_dict)
    # print(driver['_id'])
    return "vehicle got created successfully"


@app.route('/update', methods=['POST'])
def updateTable():
    incoming_msg = request.get_json()["Body"];
    updateType = incoming_msg['type'];
    # whereToDeleteOrUpdate = incoming_msg['type'][1]
    
    userId = incoming_msg['userId']
    if updateType == 'Delete':
        db["Customer"].delete_one({"_id": ObjectId(userId)})
    elif updateType == 'Update':
        updateData = incoming_msg['data'] if incoming_msg['data'] else ''
        db['Customer'].update_one({"_id": ObjectId(userId)}, {
            "$set": {
                **updateData
            }
        })
    return "updated successfully"


@app.route('/fetchTrips', methods=["GET"])
@token_required
def fetchTrips(current):
    trips = db['Driver'].find_one({'_id': ObjectId(current)})["trips"]
    return json.loads(json_util.dumps(trips)), 200

@app.route('/cancelTrip', methods=["POST"])
def cancelTrip():
    incoming_msg = request.get_json()
    bookingId = incoming_msg['bookingId']
    trip = db['Bookings'].find_one({"_id": ObjectId(bookingId)})
    date = trip['travel_date'].split(" ")[:4]
    year = date[-1]
    day = date[-2]
    
    months = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6, "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov":11, "Dec":12}
    month = months[date[1]]
    # print(months[month])
    hour = trip['trip_start_datetime'].split(":")[0]
    minutes = trip['trip_start_datetime'].split(":")[1]
    booked_date = datetime.datetime(int(year), month, int(day), int(hour), int(minutes))
    # booked_date = datetime.datetime(2024,7,24,20, 00)
    current_date = datetime.datetime.now()
    two_hours_prior = current_date - datetime.timedelta(hours=2)
    
    # print(booked_date)

    if trip['status'] == 'Booked':
        if booked_date.date() > two_hours_prior.date():
            db['Bookings'].delete_one({"_id": ObjectId(bookingId)})
            # s = db['Driver'].find_one({'trips.bookingId':ObjectId(bookingId)})
            # trip = s['trips']
            # res = list(filter(lambda x: (x['bookingId'] != ObjectId('6682de3b6ce950c144b3d4b5')), trip))

            # db['Driver'].update_one({'trips.bookingId':ObjectId(bookingId)},
            #                         {
            #                             "$set": {
            #                             "trips.$.trip_status": "Cancelled"
            #                         }
            #                         }
            #                         )
            db['Customer'].update_one({'booking_history._id': ObjectId(bookingId)}, {
            "$pull" : {
                "booking_history": {"_id": ObjectId(bookingId)}
            }
            })
        
         
            return "canceled"
        elif booked_date.date() == two_hours_prior.date() and current_date.time() < booked_date.time():
            if two_hours_prior.time() < booked_date.time():
                db['Bookings'].delete_one({"_id": ObjectId(bookingId)})
                # s = db['Driver'].find_one({'trips.bookingId':ObjectId(bookingId)})
                # trip = s['trips']
                # res = list(filter(lambda x: (x['bookingId'] != ObjectId('6682de3b6ce950c144b3d4b5')), trip))
   
                # db['Driver'].update_one({'trips.bookingId':ObjectId(bookingId)},
                #                         {
                #                             "$set": {
                #                             "trips": res
                #                         }
                #                         }
                #                         ) 
                # db['Vehicles'].update_one({"bookingId": ObjectId(bookingId)}, {
                #     "$set": {
                #         "bookingId": "",
                #         "status":"active"
                #     }
                # })
                db['Customer'].update_one({'booking_history._id': ObjectId(bookingId)}, {
            "$pull" : {
                "booking_history": {"_id": ObjectId(bookingId)}
            }
            })
                return "canceled"
            return "can't cancell"
        else:
            return "can't cancel"
    # elif trip['status'] == "trip confirmed":
    #     if booked_date.date() > two_hours_prior.date():
    #         db['Bookings'].delete_one({"_id": ObjectId(bookingId)})
    #         db['Driver'].delete_many({
    #         "trips.bookingId": ObjectId(bookingId)
    #     })
    #         db['Vehicles'].update_one({"bookingId": ObjectId(bookingId)}, {
    #                 "$set": {
    #                     "bookingId": ""
    #                 }
    #             })
    #         return "canceled"
    #     elif booked_date.date() == two_hours_prior.date() and current_date.time() < booked_date.time():
    #         if two_hours_prior.time() < booked_date.time():
    #             db['Bookings'].delete_one({"_id": ObjectId(bookingId)})
    #             db['Driver'].update_one({
    #         "trips.bookingId": ObjectId(bookingId)
    #     })
    #             # db['Driver']['status'].remove
    #             db['Vehicles'].update_one({"bookingId": ObjectId(bookingId)}, {
    #                 "$set": {
    #                     "bookingId": "",
    #                     "status": "active"
    #                 }
    #             })
    #         return "can't cancell"
    #     else:
    #         return "can't cancel"
    else: 
        return "can't cancel running trip"
    

@app.route('/reschedule', methods=['POST'])
def reschedule():
    incoming_msg = request.get_json()
    bookingId = incoming_msg['bookingId']
    startDate = incoming_msg['startDate']
    dateFormat = startDate.split(" ")[:4]
    startTiming = incoming_msg['startingTime']
    months = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6, "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov":11, "Dec":12}
    month = months[dateFormat[1]]

    exactData = datetime.datetime(int(dateFormat[-1]), month, int(dateFormat[-2]), int(startTiming.split(":")[0]), int(startTiming.split(":")[1]))

    two_hour_prios = datetime.datetime.now() - datetime.timedelta(hours=2)

    tripType = incoming_msg['tripType']
    trip = db['Bookings'].find_one({"_id": ObjectId(bookingId)})
    if exactData > datetime.datetime.now():
        if trip['status'] == 'Booked':
            if tripType == "oneWay":
                db['Bookings'].update_one({"_id": ObjectId(bookingId)}, {
                    "$set": {
                        "travel_date": startDate,
                        "trip_start_datetime": startTiming
                    }
                })
                
                db['Customer'].update_one({"booking_history._id": ObjectId(bookingId)}, {
                    "$set": {
                        "booking_history.$.travel_date": startDate,
                        "booking_history.$.trip_start_datetime": startTiming
                    }
                })
                return "rescheduled one way trip"
            elif tripType == 'roundTrip':
                endTripTime = incoming_msg['endTripTiming'] if incoming_msg['endTripTiming'] else ''
                returnDate = incoming_msg['returnDate'] if incoming_msg['endTripTiming'] else ''
                db['Bookings'].update_one({"_id": ObjectId(bookingId)}, {
                    "$set": {
                        "travel_date": startDate,
                        "trip_start_datetime": startTiming,
                        "trip_end_datetime": endTripTime,
                        "return_date": returnDate
                    }
                })
                return "rescheduled round trip"
    return "cant't reschedule"


@app.route('/updateTripStatus', methods=['POST'])
@token_required
def updateTripStatus(current):
    incoming_msg = request.get_json()
    bookingId = incoming_msg['bookingId']
    trip = incoming_msg['tripType']
    vehicleType = incoming_msg['vehicleType']
    userId = incoming_msg['userId'] if incoming_msg['userId'] else ''
    if incoming_msg['status'] == 'Driver Arrived':
        db['Bookings'].update_one({
                '_id': ObjectId(bookingId)
            }, {
                "$set": {"status": incoming_msg['status']}
            })
        db['Driver'].update_many({
        "trips.bookingId": ObjectId(bookingId)
    }, {"$set":{"trips.$.trip_status":incoming_msg['status']}})
        return "Updated to Driver Arrived"
    elif incoming_msg['status'] == 'Trip Started':
        otpUser = db['Customer'].find_one({"_id": ObjectId(userId)})['otp']
        otp = incoming_msg['otp'] if incoming_msg['otp'] else ''
        if otp == otpUser:
            db['Bookings'].update_one({
                '_id': ObjectId(bookingId)
            }, {
                "$set": {"status": incoming_msg['status']}
            })
            db['Driver'].update_many({
            "trips.bookingId": ObjectId(bookingId)
        }, {"$set":{"trips.$.trip_status":incoming_msg['status']}})
            return "Updated to Trip started"
    # {"$set":{"trips.$.trip_status":incoming_msg['status']}})
    elif incoming_msg['status'] == 'Trip Ended':
        regNumberVehicle = incoming_msg['regNum'] if incoming_msg['regNum'] else ''
        booked = db['Bookings'].find_one({"_id": ObjectId(bookingId)})
        zoneName = booked['orginZone']
        bookedPrice = booked['total_trip_price']
        bookedDistance = booked['distance']
        bookedDuration = int(booked['duration'])
        duration = incoming_msg['duration'] if incoming_msg['duration'] else ''
        distance = incoming_msg['distance'] if incoming_msg['distance'] else ''
        driverId = incoming_msg['driverId'] if incoming_msg['driverId'] else ''
        db['Vehicles'].update_one({
            'registration_number': regNumberVehicle
        }, {
            "$set": {"status": "active", "bookingId": ""}
        })
        db['Driver'].update_one({
            '_id': ObjectId(driverId)
        }, {
            "$set": {"status": "active"}
        })
        db['Driver'].update_many({
        "trips.bookingId": ObjectId(bookingId)
    }, {"$set":{"trips.$.trip_status":incoming_msg['status']}})
        db['Bookings'].update_one({"_id": ObjectId(bookingId)}, {
                "$set": {"status": incoming_msg['status']}
        })
        price = calculateLastPrice(zoneName, distance, duration, trip, vehicleType)
        extraKm = distance - bookedDistance if distance > bookedDistance else 0
        extraDuration = duration - bookedDuration if duration > bookedDuration else 0

        return json.loads(json_util.dumps({"Amount": price, 
                "booked_price": bookedPrice, 
                "distance_traveled": distance, 
                "duration": duration, 
                "booked_distance": bookedDistance, 
                "booked_duration":bookedDuration,
                "extraKms": extraKm,
                "extraHours": extraDuration})) 
        
    return "otp not valid", 500


@app.route('/getPrice', methods=['POST'])
def getPrice():
    incoming_msg = request.get_json()["Body"];
    origin = incoming_msg['origin_zone']
    destination = incoming_msg['destination']
    tripType = incoming_msg['trip_type']
    userId = incoming_msg['user_id']
    zoneName = incoming_msg['origin_zone'].upper()
    zone = db['Zone']
    user = db['Customer'].find_one({"_id": ObjectId(userId)})

    my_dist = gmaps.distance_matrix(origin,destination)['rows'][0]['elements'][0]
    distance = my_dist['distance']['text'].split(' ')[0].replace(',', '')
    twoWayDistancecal = gmaps.distance_matrix(destination,origin)['rows'][0]['elements'][0]
    twoWayDistance = twoWayDistancecal['distance']['text'].split(' ')[0].replace(',', '')
    durationHours = my_dist['duration']['text'].split(' ')[0] if tripType == 'oneWay' else incoming_msg['trip_duration'].split(' ')[0]
    durationMinutes = my_dist['duration']['text'].split(' ')[2] if tripType == 'oneWay' else incoming_msg['trip_duration'].split(' ')[2]
    allDuration = int(durationHours) if int(durationMinutes) == 0 else int(durationHours) + 1
    
    if user:
        price = calculateOneWayPricing(zoneName, int(float(distance)), allDuration, tripType, twoWayDistance)
        
        payload = {
        'originZone': zoneName,
        'toLocation': destination,
        'duration': allDuration,
        'distance': int(float(distance)) if tripType == 'oneWay' else int(float(distance) + float(twoWayDistance)),
        "price": price

        }
        db['Customer'].update_one(
            {'_id': ObjectId(userId)},
            {
                "$push": {
                    "search_history": payload
                }
            }
            )
        return payload

    else:
        price = calculateOneWayPricing(zoneName, int(float(distance)), allDuration, tripType, twoWayDistance)
        payload = {
         'originZone': zoneName,
        'toLocation': destination,
        'duration': allDuration,
        'distance': int(float(distance)) if tripType == 'oneWay' else int(float(distance) + float(twoWayDistance)),
        "price": price

    }
        return  payload
    


def calculateLastPrice(zone, distance, duration,trip, vehicleType):
    zoneName = db['Zone'].find_one({"zone_name": zone})
    price = 0
    
    if trip == 'oneWay':
        for i in zoneName[vehicleType]['hourly_price']:
            r = range(int(i['from']), int(i['to']))
            if duration in r:
                price = (int(i['price']) * duration) + (int(zoneName[vehicleType]['price_per_km']) * distance)
                break
    elif trip == "roundTrip":
        for i in zoneName[vehicleType + "_round"]['hourly_price_round']:
            r = range(int(i['from']), int(i['to']))
            if duration in r:
                price = (int(i['price']) * duration) + (int(zoneName[vehicleType]['price_perkm_round']) * distance)
                break
    return price





def calculateOneWayPricing(nameZone, distance, duration, trip, twoWayDistance=0):
    zone = db["Zone"]
    # name = nameZone.upper()
    zoneName = zone.find_one({'zone_name':nameZone})
    vehicles = db['Vehicles'].find({"zone_id": zoneName['_id']})
    cars = []
    for i in list(vehicles):
        # print(i['vehicle_type'])
        cars.append(i['vehicle_type'])
    
    global farePrice
    if duration in range(0,24):
        farePrice = 500
    elif duration in range(24,48):
        farePrice = 1000
    elif duration in range(48, 72):
        farePrice = 1500
    else:
        farePrice = 2000
    fareDetails = {
        "driverAllowance": farePrice
    }
    extraHours = {
    }
    price = {
        "fareDetails": fareDetails,
        "hours": extraHours
    }
    

                    
    
    if trip == 'oneWay':
        for i in cars:
            extraHours[i] = []
            if i in zoneName.keys():
                for j in zoneName[i]['hourly_price']:
                    # print( type(j['from']), type(j['to']))
                    r = range(int(j['from']), int(j['to']))
                    if duration not in r: 
                        extraHours[i].append(int(j['price']))
                    
                    if duration in r:
                        # print(int(zoneName[i]['price_per_km']))
                        extraHours[i].append([int(j['price'])])
                        price[i] = (int(j['price']) * duration) + (int(zoneName[i]['price_per_km']) * distance)
                        fareDetails[i] = [ int(j['price']) * duration, int(zoneName[i]['price_per_km']) * distance]
                    
                        

    elif trip == 'roundTrip':
        distance = distance + int(float(twoWayDistance))
        for i in cars:
            extraHours[i + "_round"] = []
            if i + '_round' in zoneName.keys():
                for j in zoneName[i + "_round"]['hourly_price_round']:
                    # print( type(j['from']), type(j['to']))
                    r = range(int(j['from']), int(j['to']))
                    if duration not in r: 
                        extraHours[i + "_round"].append(int(j['price']))
                    if duration in r:
                        extraHours[i + "_round"].append([int(j['price'])])
                        price[i] = (int(j['price']) * duration) + (int(zoneName[i + "_round"]['price_perkm_round']) * distance)

                        fareDetails[i] = [ int(j['price'])  * duration, int(zoneName[i + '_round']['price_perkm_round'])  * distance]

    return price

    


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
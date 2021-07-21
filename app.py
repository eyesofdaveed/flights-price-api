from logging import error
import requests
from flask import Flask, request
from flask_caching import Cache  # Import Cache from flask_caching module
import datetime
import calendar
import json
import time
import atexit
from apscheduler.schedulers.background import BackgroundScheduler

""" Initalize flask with basic configuration and redis """
app = Flask(__name__)
app.config.from_object('config.BaseConfig')
cache = Cache(app)

""" URLs to request data from kiwi API """
URL_BOOKING_TOKEN = "https://api.skypicker.com/flights?v=3&partner=eyesofdaveedaviatatest&one_per_date=1&curr=kzt"
URL_FLIGHT_PRICE = "https://booking-api.skypicker.com/api/v0.1/check_flights?v=2&currency=KZT&bnum=1&pnum=1&v=2&affily=eyesofdaveedaviatatest&adults=1"

""" Checks if the flight is valid, if so returns the total cost """
def getPriceForBookingToken(booking_token):
    flight_status_check = False

    """ It will make 12 request calls with 10 secs interval or untill
    it gets flight_checked true as a response """
    max_number_of_checks = 12
    flight_price = 0

    while flight_status_check == False and max_number_of_checks > 0:
        r = requests.get(f"{URL_FLIGHT_PRICE}&booking_token={booking_token}", timeout=10)

        if r.status_code == requests.codes.ok:
            """ Convert the response into the dictionary to retrieve flight_status """
            try:
                """ Try to get flight_checked from the response if found get the price
                or wait 10 secs to make another request for flight_checked """
                booking_token_response_dict = json.loads(r.text)
                flight_status = booking_token_response_dict["flights_checked"]
                flight_status_check = flight_status
                if flight_status_check:
                    flight_price = booking_token_response_dict["conversion"]["amount"]
                else:
                    time.sleep(10)
            except Exception as ex:
                print(ex)
        else:
            print(r.status_code)
        max_number_of_checks -= 1
        """ Close the request """
        r.close()

    """ If valid retrieve the converted price and return it """
    return flight_price

""" The amount of time data is stored inside of cache """
set_timeout = 24 * 3600

@app.route("/<direction>")
@cache.cached(timeout=set_timeout, query_string=True)
def cacheFlightPrices(direction):

    """ Get flight directions upon a request """
    city_codes = direction.split("-")
    city_from = str(city_codes[0].upper())
    city_to = str(city_codes[1].upper())
    
    URL_TO_CHECK = URL_BOOKING_TOKEN + f"&fly_from={city_from}&fly_to={city_to}"
    
    """ Get today's date upon a request """
    today = datetime.datetime.now()
    day_of_request = today.day + 1
    month_of_request = today.month
    year_of_request = today.year

    """ Total days of current month """
    days_in_current_month = calendar.monthrange(year_of_request, month_of_request)[1]

    dict_with_prices_to_be_cached = {}

    """ For the next 30 days """
    for _ in range (0,30):

        """ Combine all string to finalize the URL to be requested """
        date_to_check = f"{str(day_of_request)}/{str(month_of_request)}/{str(year_of_request)}"
        r = requests.get(f"{URL_TO_CHECK}&date_from={date_to_check}&date_to={date_to_check}", timeout=5)

        """ Print to the console the direction and date currently requested """
        print(f"Fetching -> {direction}: {date_to_check}")

        if r.status_code == requests.codes.ok:
            """ Convert the response into the dictionary to retrieve booking_token value """
            flight_response_dict = json.loads(r.text)
            try:
                booking_token = flight_response_dict["data"][0]["booking_token"]
                actual_flight_price = getPriceForBookingToken(booking_token)
                temp_dict = {date_to_check:actual_flight_price}
                dict_with_prices_to_be_cached.update(temp_dict)
                print("Cache was updated with the new entry")
            except Exception as ex:
                print(ex)
        else:
            print(r.status_code)
        r.close()

        """ Simple logic to traverse the calendar """
        if day_of_request + 1 > days_in_current_month:
            day_of_request = 1
            if month_of_request + 1 > 12:
                month_of_request = 1
                year_of_request += 1  
            month_of_request += 1
        else:
            day_of_request += 1

    print("Fetching completed succesfully")
    
    """ Dump everything onto the API with the requested direction """
    return json.dumps(dict_with_prices_to_be_cached)

""" Triggers a request on API for each flight direction """
def dailyUpdater():
    """ List of all flight directions """
    list_of_flight_directions = [
    "ALA-TSE", 
    "TSE-ALA", 
    "ALA-MOW",
    "MOW-ALA",
    "ALA-CIT",
    "CIT-ALA",
    "TSE-MOW",
    "MOW-TSE",
    "TSE-LED",
    "LED-TSE"
]

    """ Clear up the cache first """
    with app.app_context():
        cache.clear()

    for flights in list_of_flight_directions:
        """ Request for each flight direction with the maximum timeout of 3600 secs """
        r = requests.get(f"http://127.0.0.1:5000/{flights}", timeout=3600)
        if r.status_code == requests.codes.ok:
            pass

""" Initialize updater of cache on noon of each day """
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(dailyUpdater, trigger='cron', hour='00', minute='00', replace_existing=True)
scheduler.start()

""" Shut down the scheduler when exiting the app """
atexit.register(lambda: scheduler.shutdown())

""" Start the app """
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

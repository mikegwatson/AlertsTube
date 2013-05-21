#! /usr/bin/python3
#
#  AlertsTube.py
#  
#  Copyright 2013  
#  
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#  
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
import requests
import os
import select
import re
import threading
import subprocess
import sys
import queue
import imaplib
import email
import json
import datetime
import time
from threading import Thread
from pigredients.ics import ws2801 as ws2801                	# Forked version of https://github.com/rasathus/pigredients
from weatheralerts import WeatherAlerts                     	# https://github.com/zebpalmer/WeatherAlerts


KEY = 'YOUR_KEY_GOES_HERE' 	# Get your Weather Underground Developer key at: http://www.wunderground.com/weather/api/d/pricing.html 
LOCATION = 'MA/Wellesley'  	# State and City to fetch weather forecast
MY_SAME_CODE = '025021'    	# Get your area's SAME code at: http://www.nws.noaa.gov/nwr/indexnw.htm#sametable
ALERT_SEVERITY = 'minor'   	# Options: 'severe' | 'major' | 'moderate' | 'minor', determines what type of event triggers a weather alert 
PRECIP_THRESHOLD = 40      	# 40 means show an alert when chance of precipitation is greater than 40% 
CHECK_DELAY = 600          	# Number of seconds to wait before checking the weather again, 600s = a 10 min delay
ALERT_SOUND = True         	# If True then play the alert sound when a new weather alert is issued
CHECK_EMAILS = True        	# If True then check an email account for new alerts via ifttt.com or other source
EMAIL_ADDRESS = 'YOUR_ACCOUNT_NAME@gmail.com'                	# Email account to check
EMAIL_PASSWD = 'YOUR_PASSWORD'                                 	# Email account password

# URL to fetch current conditions
ApiUrl1 = \
  'http://api.wunderground.com/api/' + KEY + '/geolookup/conditions/q/' + LOCATION + '.json' 
# URL to fetch the forecast
ApiUrl2 = \
  'http://api.wunderground.com/api/' + KEY + '/forecast/q/' + LOCATION + '.json'  


def setup_and_register_interrupts():
    global po
    # Setup GPIO Pins using P1 board header pins so we can use interrupts
    os.system('echo 4 > /sys/class/gpio/export')                # GPIO export P1 pin 7 for GPIO
    os.system('echo 23 > /sys/class/gpio/export')               # GPIO export P1 pin 16 for GPIO
    os.system('echo 24 > /sys/class/gpio/export')               # GPIO export P1 pin 18 for GPIO
    os.system('echo 25 > /sys/class/gpio/export')               # GPIO export P1 pin 22 for GPIO
    # Setup GPIO 4, set direction to in with a rising edge
    init4 = '/sys/class/gpio/gpio4/'
    f4 = open(init4 + 'value', 'r')
    f = open(init4 + 'direction', 'w')
    f.write('in')
    f.close()
    f = open(init4 + 'edge', 'w')
    f.write('rising')
    f.close()
    # Setup GPIO 23, set direction to in with a rising edge
    init23 = '/sys/class/gpio/gpio23/'
    f23 = open(init23 + 'value', 'r')
    f = open(init23 + 'direction', 'w')
    f.write('in')
    f.close()
    f = open(init23 + 'edge', 'w')
    f.write('rising')
    f.close()
    # Setup GPIO 24, set direction to in with a rising edge
    init24 = '/sys/class/gpio/gpio24/'
    f24 = open(init24 + 'value', 'r')
    f = open(init24 + 'direction', 'w')
    f.write('in')
    f.close()
    f = open(init24 + 'edge', 'w')
    f.write('rising')
    f.close()
    # Setup GPIO 25 set direction to out
    init25 = '/sys/class/gpio/gpio25/'
    f25 = open(init25 + 'value', 'r')
    f = open(init25 + 'direction', 'w')
    f.write('out')
    f.close()
    # Create polling object and register GPIO pins 
    po = select.epoll()                                     	# Return polling object which can be registered and unregistered
    po.register(f4, select.POLLPRI)                         	# register f4 for polling
    po.register(f23, select.POLLPRI)                        	# register f23 for polling
    po.register(f24, select.POLLPRI)                        	# register f24 for polling
    return f4, f23, f24


def read_GPIO(f4, f23, f24):
  while True:
    try: 
      events = po.poll(.25)                                 	# Returns status of registered file descriptors from above, wait .25 sec for GPIO change
      f4.seek(0)                                            	# Reset location to beginning of file 
      f4state_last = f4.read(1)                             	# Read GPIO4 pin state
      f23.seek(0)                                           	# Reset location to beginning of file 
      f23state_last = f23.read(1)                           	# Read GPIO23 pin state
      f24.seek(0)                                           	# Reset location to beginning of file 
      f24state_last = f24.read(1)                           	# Read GPIO24 pin state   
      return events, f4, f23, f24
    except:                                                 	# If we get an error wait a bit and try again
      time.sleep(.25)
      continue
    break  
 

def solid_LED(R,G,B,intensity):                             	# Display solid LED pattern
    led_chain = ws2801.WS2801_Chain()
    led_chain.set_ic(ic_id=0, rgb_value=[R,G,B], lumi=intensity)# Set 1st of 2 LEDs used
    led_chain.set_ic(ic_id=1, rgb_value=[R,G,B], lumi=intensity)# Set 2nd of 2 LEDs used
    led_chain.write()                                       	# Write LED commands over SPI bus
    led_chain.close()   


def flicker_LED(R,G,B,intensity):                           	# Display flickering snow LED pattern for ~2 seconds
    total_sleeptime = 0
    led_chain = ws2801.WS2801_Chain()
    while total_sleeptime < 2:
      led_chain.set_ic(ic_id=0, rgb_value=[R,G,B], lumi=int(random.uniform(4, 16)))
      led_chain.set_ic(ic_id=1, rgb_value=[R,G,B], lumi=int(random.uniform(4, 16)))
      led_chain.write()
      sleeptime = random.uniform(0, 1)
      total_sleeptime = total_sleeptime + sleeptime 
      time.sleep(sleeptime)
    led_chain.close()   


def blink_LED(R,G,B,intensity):                             	# Display blink LED pattern
    led_chain = ws2801.WS2801_Chain()
    led_chain.all_off()
    led_chain.write()
    time.sleep(.5)
    led_chain.set_ic(ic_id=0, rgb_value=[R,G,B], lumi=100)
    led_chain.set_ic(ic_id=1, rgb_value=[R,G,B], lumi=100)
    led_chain.write()
    time.sleep(.5)
    led_chain.close()   


def snooze_LED(R,G,B,intensity):                            	# Display growing and shrinking LED pattern
    led_chain = ws2801.WS2801_Chain()
    led_chain.all_off()
    led_chain.write() 
    for i in range(0,80):
      led_chain.set_ic(ic_id=0, rgb_value=[R,G,B], lumi=i)
      led_chain.set_ic(ic_id=1, rgb_value=[R,G,B], lumi=i)
      led_chain.write()
      if (i < 20):                                          	# Decelerate as get closer to zero
        time.sleep(0.035)
      else:
        time.sleep(0.02)
    time.sleep(.2) 
    for j in range(80,-1,-1):
      led_chain.set_ic(ic_id=0, rgb_value=[R,G,B], lumi=j)
      led_chain.set_ic(ic_id=1, rgb_value=[R,G,B], lumi=j)
      led_chain.write()
      if (j < 20):                                          	# Decelerate as get closer to zero
        time.sleep(0.035)
      else:
        time.sleep(0.02)
    led_chain.close()   
    time.sleep(.5)


def off_LED():                                              	# Turn off LEDs
    led_chain = ws2801.WS2801_Chain()
    led_chain.all_off()
    led_chain.write()
    led_chain.close()


def weather_alert(nws):                                     	# Check to see if there is a weather alert currently
    global title, severity, summary
    while True:
      try:
        nws.refresh()                                       	# Check to see if cache has expired, if so then pull a new copy of the feed. 
      except:                                               	# If we get an error wait a bit and try again
        print('Failed to weather alerts, trying again in 30 seconds...')
        time.sleep(30)
        continue
      break  
    if len(nws.alerts) > 0:                                 	# If there are alerts then save them into title, summary and severity 
      for weatheralrt in nws.alerts:
        title = (weatheralrt.title)
        summary = (weatheralrt.summary)
        severity = (weatheralrt.severity)
      if 'severity' in globals():                           	# If there's an alert then check the severity
        if ALERT_SEVERITY == "severe":
          if re.search('severe', severity, re.IGNORECASE):
            return True
          else:
            return False
        if ALERT_SEVERITY == "major":
          if re.search('major', severity, re.IGNORECASE) or re.search('severe', severity, re.IGNORECASE):
            return True
          else:
            return False
        if ALERT_SEVERITY == "moderate":    
          if re.search('moderate', severity, re.IGNORECASE) or re.search('major', severity, re.IGNORECASE) or \
re.search('severe', severity, re.IGNORECASE):
            return True
          else:
            return False
        if ALERT_SEVERITY == "minor":    
          if re.search('minor', severity, re.IGNORECASE) or re.search('moderate', severity, re.IGNORECASE) or \
re.search('major', severity, re.IGNORECASE) or re.search('severe', severity, re.IGNORECASE):
            return True
          else:
            return False    
      else:
        return False
    else:
      title = ""
      summary = ""
      severity = ""  
      return False

def fetch_mail():  
  global calendar_alert
  calendar_alert = False                                        # set calendar_alert to False be default, change if find calendar alert
  if CHECK_EMAILS:  
    date = (datetime.date.today() - datetime.timedelta(1)).strftime("%d-%b-%Y") # timedelta is number of days back to search for email, currently 1 day 
    imap = imaplib.IMAP4_SSL('imap.gmail.com')                  # Fetch the mail from imap.gmail.com
    while True:
      try:
        imap.login(EMAIL_ADDRESS,EMAIL_PASSWD)
        imap.select()
        result, data = imap.search(None, '(FROM \"action@ifttt.com\") (SENTSINCE {date})'.format(date=date)) # Show all emails from action@ifttt.com sent within last X days
        #result, data = imap.search(None, "ALL")
        for num in data[0].split():
          result, data = imap.fetch(num, "(RFC822)")            # Fetch the email body (RFC822) for the given ID
          raw_email = data[0][1]                                # Email raw text including headers
          msg = email.message_from_string(raw_email.decode('utf-8'))
          payload = msg.get_payload()
          if type(payload) is str:
            msg_payload = payload
          elif type(payload) is list:
            for part in msg.walk():
              if part.get_content_type() == 'text/plain':       # If the email is plain text then parse it 
                msg_payload = part.get_payload()

                #### CHECK EMAIL FOR IFTTT STOCK PRICE ####
                if re.search('Personal Recipe 3430936', msg_payload, re.IGNORECASE): # Search for Personal Recipe # from IFTTT
                  alert_string = msg_payload.split('\n', 1)[0]  # Store the first line of text from the email 
                  print("Stock Alert: " + alert_string.replace("<br>", "")) # Print the first line and remove <br>
                  imap.store(num, '+FLAGS', '\\Deleted')        # Delete the message now that we've read it
                  payload = {'voice': 'lauren', 'txt': alert_string.replace("<br>", ""), 'speakButton': 'SPEAK'}
                  r3 = requests.post("http://192.20.225.36/tts/cgi-bin/nph-nvdemo", data=payload) # Post message data for text to speech
                  with open("stockalert.wav", "wb") as code:    # Save text to speech .wav file
                    code.write(r3.content)
                  os.system('aplay stockalert.wav > /dev/null 2>&1 &') # Play stock alert in background and trash the text
                  #print('SUBJECT: ' + msg['SUBJECT'])

                #### CHECK EMAIL FOR IFTTT CALENDAR EVENTS ####
                if re.search('Personal Recipe 3439586', msg_payload, re.IGNORECASE): # Search for Personal Recipe # from IFTTT
                  alert_string = msg_payload.split('\n', 1)[0]  # Store the first line of text from the email 
                  print("Calendar Alert: " + alert_string.replace("<br>", ""))
                  calendar_alert = True	                        # set calendar_alert to True now that we've found an even
                  imap.store(num, '+FLAGS', '\\Deleted')        # Delete the message now that we've read it

        imap.expunge()                                          # perform email message deletions
        imap.close()                                            # close the imap session and then logout
        imap.logout()
      except:                                                  	# If we get an error wait a bit and try again
        print('Failed to fetch mail, trying again in 30 seconds...')
        time.sleep(30)
        continue
      break  


def fetch_weather(nws):
    global today, tonight, tomorrow, poptoday, poptonight, poptomorrow, active_weather_alert, last_weather_alert, ALERT_SOUND, current, temp
    while True:
      try:
        r1 = requests.get(ApiUrl1)                              # Fetch current conditions from the web             
        conditions = r1.json()
        temp = int(float(conditions['current_observation']['temp_f'])) # Remove decimal point for all temperatures
        current = conditions['current_observation']['weather']  # Current conditions 
        r2 = requests.get(ApiUrl2)                              # Fetch the forecast from the web    
        forecast = r2.json()
      except:                                                   # If we get an error wait a bit and try again
        print('Failed to fetch weather, trying again in 30 seconds...')
        time.sleep(30)
        continue
      break  													                          # break out of while loop only when fetching weather succeeds

    os.system('clear')                                          # Clear the terminal screen
    if weather_alert(nws):
      active_weather_alert = True 
      if aplay_not_active() and last_weather_alert == False and ALERT_SOUND: 
        os.system('aplay alert.wav > /dev/null 2>&1 &')         # Play new alert sound in the background and trash text
        time.sleep(1)  
      headlines = ''.join(re.findall ( '^\.\.\.(.*?)\.\.\.', summary, re.MULTILINE)) # Alert Headline grab text between ... and ...  
      today = "It's " + time.strftime("%I:%M %p", time.localtime(time.time())) + ", %s and %s degrees." % (current, temp) \
+ '\n\033[91m' + severity + ' Alert: ' + title + ', ' + headlines + '\033[98m' + '\033[0m'  # Add color escape codes for colored text in terminal
      today = expand_and_format(today)                          # Expand and format weather alert
      print('\n' + today + '\n\n' + '\033[91m' + summary + '\033[98m' + '\033[0m')  # display current weather alert
    else:
      active_weather_alert = False
      currenthour = int(time.strftime("%H", time.localtime()))
      if currenthour < 18:                                      # If it's before 18:00 hours (i.e. 6pm) then today's forecast otherwise tonight's forecast 
        # today = current time, conditions & temp + today's forecast
        today = "It's " + time.strftime("%I:%M %p", time.localtime(time.time())) + ", %s and %s degrees" % (current, temp) \
          + ".\nToday: " + forecast['forecast']['txt_forecast']['forecastday'][0]['fcttext']
      else:
        # today = current time, conditions & temp + tonight's forecast
        today = "It's " + time.strftime("%I:%M %p", time.localtime(time.time())) + ", %s and %s degrees" % (current, temp) \
          + ".\nTonight: " + forecast['forecast']['txt_forecast']['forecastday'][1]['fcttext']
      today = expand_and_format(today)                          # Expand and format today / tonight
      print('\n' + today)                                       # Display today's forecast
    last_weather_alert = active_weather_alert
    # tomorrow = current time, conditions & temp + tomorrow's forecast
    tomorrow = "It's " + time.strftime("%I:%M %p", time.localtime(time.time())) + ", %s and %s degrees" % (current, temp) \
      + ".\nTomorrow: " + forecast['forecast']['txt_forecast']['forecastday'][2]['fcttext']
    tomorrow = expand_and_format(tomorrow)                      # Expand and format tomorrow
    poptomorrow = forecast['forecast']['txt_forecast']['forecastday'][2]['pop']     # tomorrow's chance of precipitation
    print('\n' + tomorrow + '\n')                               # Display tomorrow's forecast


def fetch_timer(nws):
    global t
    fetch_weather(nws)                                          # Fetch the weather and see if there is an alert
    fetch_mail()                                                # Fetch the mail and see if there is an alert
    t = threading.Timer(CHECK_DELAY, fetch_timer, [nws])        # Wait CHECK_DELAY number of seconds before running this function again
    t.start()


def rain_tomorrow():                                            # Check to see if it's going to rain tomorrow  
    if re.search('rain', tomorrow.split('\n', 1)[1], re.IGNORECASE) and int(poptomorrow) >= PRECIP_THRESHOLD:
      return True                                               # Don't check 1st line since it has current conditions 
    else: 
      return False


def snow_tomorrow():                                            # Check to see if it's going to snow tomorrow
    if re.search('snow', tomorrow.split('\n', 1)[1], re.IGNORECASE) and int(poptomorrow) >= PRECIP_THRESHOLD:
      return True                                               # Don't check 1st line since it has current conditions 
    else: 
      return False


def cloudy_tomorrow():                                          # Check to see if it's going to be cloudy tomorrow 
    if (re.search('cloudy', tomorrow.split('\n', 1)[1], re.IGNORECASE) or re.search('overcast', tomorrow.split('\n', 1)[1], re.IGNORECASE)) and int(poptomorrow) < PRECIP_THRESHOLD:
      return True                                               # Don't check 1st line since it has current conditions 
    else: 
      return False


def sunny_tomorrow():                                           # Check to see if it's going to be sunny tomorrow
    if (re.search('sunny', tomorrow.split('\n', 1)[1], re.IGNORECASE) or re.search('clear', tomorrow.split('\n', 1)[1], re.IGNORECASE)) and int(poptomorrow) < PRECIP_THRESHOLD:
      return True                                               # Don't check 1st line since it has current conditions  
    else: 
      return False


def expand_and_format(string):                                  # Expand and format text to get rid of any weirdness with text to speech 
    string = string.replace("mph", "miles per hour")
    string = string.replace(" 10", ", 10")                      # Say 'ten' correctly
    string = string.replace("High", "High,")                    # Say 'High' correctly
    string = string.replace("and", "and,")                      # Say 'and' correctly
    string = string.replace(" in. ", " inches ")                # Say inches
    string = string.replace("Watch", "Watch,")                  # Say 'Watch' correctly
    string = re.sub(r'Winds from the .* at', r'Winds', string)  # Remove wind direction text
    string = string.replace(" N ", " North ")
    string = string.replace(" NNE ", " North-northeast ")   
    string = string.replace(" NE ", " NorthEast ")
    string = string.replace(" ENE ", " East-northeast ")
    string = string.replace(" E ", " East ")
    string = string.replace(" ESE ", " East-southeast ")
    string = string.replace(" SE ", " SouthEast ")
    string = string.replace(" SSE ", " South-southeast ")
    string = string.replace(" S ", " South ")
    string = string.replace(" SSW ", " South-southwest ")
    string = string.replace(" SW ", " Southwest ")
    string = string.replace(" WSW ", " West-southwest ")
    string = string.replace(" W ", " West ")
    string = string.replace(" WNW ", " West-northwest ")
    string = string.replace(" NW ", " Northwest ")
    string = string.replace(" NNW ", " North-northwest ")
    string = re.sub(r'(\d{1,3})F', r'\1', string)               # Remove F from temperatures - all temps in USA are F
    string = string.replace(" by NWS", "")                      # Strip by NWS, we don't care who the alert is by
    return(string)


def play_tomorrows_forecast(nws):
    os.system('aplay confirm.wav > /dev/null 2>&1 &')           # Play confirm click in background and trash text
    fetch_weather(nws)
    # Convert forecast to Speech
    payload = {'voice': 'lauren', 'txt': tomorrow, 'speakButton': 'SPEAK'}
    r3 = requests.post("http://192.20.225.36/tts/cgi-bin/nph-nvdemo", data=payload)  # post data for text to speech
    with open("tomorrow.wav", "wb") as code:                    # Save text to speech .wav file  
      code.write(r3.content)
    os.system('aplay tomorrow.wav > /dev/null 2>&1 &')          # Play tomorrow's forecast in background and trash text 


def play_todays_forecast(nws): 
    os.system('aplay confirm.wav > /dev/null 2>&1 &')           # Play confirm click in background and trash text 
    fetch_weather(nws)
    today1 = today.replace('\033[91m', '')                      # Strip color escape codes before speaking text
    today2 = today1.replace('\033[98m', '')                     # Strip color escape codes before speaking text
    today3 = today2.replace('\033[0m', '')                      # Strip color escape codes before speaking text
    # Convert forecast to Speech 
    payload = {'voice': 'lauren', 'txt': today3, 'speakButton': 'SPEAK'}
    r3 = requests.post("http://192.20.225.36/tts/cgi-bin/nph-nvdemo", data=payload)  # post data for text to speech
    with open("today.wav", "wb") as code:                       # Save text to speech .wav file
      code.write(r3.content)
    os.system('aplay today.wav > /dev/null 2>&1 &')             # Play today's forecast in background and trash text 


def aplay_not_active():
    proc = subprocess.Popen(['pgrep', 'aplay'], stdout=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    psid = str(stdout)
    psid = psid.replace("b'", "")
    try:
      psid = int(psid.replace("\\n'",""))
      return False
    except:
      return True


def display_events(LEDcommands, SolidLastLEDcmds):
    global active_weather_alert
    # LED options are solid|snooze|blink|off RRR GGG BBB intensity(0-100) RRR|GGG|BBB take values between 0-255
    if rain_tomorrow():
      if ["solid", 65, 198, 250, 100] not in LEDcommands:       # If rain tomorrow and it's not in the LEDcommands list then 
        LEDcommands.append(["solid", 65, 198, 250, 100])        # Add light blue rain to the LED to-do list 
    else:
      if ["solid", 65, 198, 250, 100] in LEDcommands:           # Else if it's not raining tomorrow and it's in the LEDcommands list then
        LEDcommands.remove(["solid", 65, 198, 250, 100])        # Remove light blue rain from the LED to-do list
        SolidLastLEDcmds = []  
 
    if snow_tomorrow():
      if ["flicker", 255, 255, 255, 100] not in LEDcommands:    # If snow tomorrow and it's not in the LEDcommands list then 
        LEDcommands.append(["solid", 255, 255, 255, 100])       # Add light blue rain to the LED to-do list 
    else:
      if ["flicker", 255, 255, 255, 100] in LEDcommands:        # Else if it's not snowing tomorrow and it's in the LEDcommands list then
        LEDcommands.remove(["solid", 255, 255, 255, 100])       # Remove white snow from the LED to-do list
        SolidLastLEDcmds = []  

    if cloudy_tomorrow():
      if ["solid", 128, 128, 160, 32] not in LEDcommands:       # If cloudy tomorrow and it's not in the LEDcommands list then 
        LEDcommands.append(["solid", 128, 128, 160, 32])        # Add gray clouds to the LED to-do list 
    else:
      if ["solid", 128, 128, 160, 32] in LEDcommands:           # Else if it's not cloudy tomorrow and it's in the LEDcommands list then
        LEDcommands.remove(["solid", 128, 128, 160, 32])        # Remove gray clouds from the LED to-do list
        SolidLastLEDcmds = []  

    if sunny_tomorrow():
      if ["solid", 255, 200, 3, 100] not in LEDcommands:        # If sunny tomorrow and it's not in the LEDcommands list then 
        LEDcommands.append(["solid", 255, 200, 3, 100])         # Add yellow sun to the LED to-do list 
    else:
      if ["solid", 255, 200, 3, 100] in LEDcommands:            # Else if it's not sunny tomorrow and it's in the LEDcommands list then
        LEDcommands.remove(["solid", 255, 200, 3, 100])         # Remove yellow sun from the LED to-do list
        SolidLastLEDcmds = []  

    if active_weather_alert:
      if ["blink", 255, 0, 0, 100] not in LEDcommands:          # If weather alert and it's not in the LEDcommands list then 
        LEDcommands.append(["blink", 255, 0, 0, 100])           # Add red alert to the LED to-do list 
    else:
      if ["blink", 255, 0, 0, 100] in LEDcommands:              # Else if it's not a weather alert and it's in the LEDcommands list then
        LEDcommands.remove(["blink", 255, 0, 0, 100])           # Remove red alert from the LED to-do list
        SolidLastLEDcmds = []  

    if calendar_alert:
      if ["blink", 0, 0, 255, 100] not in LEDcommands:          # If calendar alert and it's not in the LEDcommands list then 
        LEDcommands.append(["blink", 0, 0, 255, 100])           # Add blue alert to the LED to-do list 
    else:
      if ["blink", 0, 0, 255, 100] in LEDcommands:              # Else if it's not a calendar alert and it's in the LEDcommands list then
        LEDcommands.remove(["blink", 0, 0, 255, 100])           # Remove blue alert from the LED to-do list 
        SolidLastLEDcmds = [] 

    if not LEDcommands:                                         # If there are no LED commands in the list then turn off the LEDs
      LEDcommands.append(["off", 0, 0, 0, 0])     

    for line in range(len(LEDcommands)):                        # Cycle through all the pending LED commands
      if LEDcommands:                                           # Make sure there's at least one command to display
        if len(LEDcommands) > 1:                                # If there's multiple commands then display the LED seqence
          if (LEDcommands[line][0] == "solid"):                 # If solid command encountered then display the solid_LED sequence
            solid_LED(int(LEDcommands[line][1]),int(LEDcommands[line][2]),int(LEDcommands[line][3]),int(LEDcommands[line][4]))
            SolidLastLEDcmds = LEDcommands						          # Save the last set of LED Commands
            time.sleep(2.0)                                     # If only 1 command and not changed then do nothing : stops LED flicker
        elif SolidLastLEDcmds != LEDcommands:                   # If there's 1 command and command changed then display the solid_LED sequence
          if (LEDcommands[line][0] == "solid"):                 # If solid command encountered then display the solid_LED sequence
            solid_LED(int(LEDcommands[line][1]),int(LEDcommands[line][2]),int(LEDcommands[line][3]),int(LEDcommands[line][4]))
            SolidLastLEDcmds = LEDcommands
            time.sleep(2.0)
        if line < len(LEDcommands):								              # This line needed for timing reasons when an LED sequence is removed
          if (LEDcommands[line][0] == "blink"):                 # If blink command encountered then display the blink_LED sequence 
            blink_LED(int(LEDcommands[line][1]),int(LEDcommands[line][2]),int(LEDcommands[line][3]),int(LEDcommands[line][4]))
            blink_LED(int(LEDcommands[line][1]),int(LEDcommands[line][2]),int(LEDcommands[line][3]),int(LEDcommands[line][4]))
        if line < len(LEDcommands):								              # This line needed for timing reasons when an LED sequence is removed
          if (LEDcommands[line][0] == "flicker"):               # If flicker command encountered then display the flicker_LED sequence 
            flicker_LED(int(LEDcommands[line][1]),int(LEDcommands[line][2]),int(LEDcommands[line][3]),int(LEDcommands[line][4]))  
        if line < len(LEDcommands):								              # This line needed for timing reasons when an LED sequence is removed
          if (LEDcommands[line][0] == "snooze"):                # If snooze command encountered then display the snooze_LED sequence
            snooze_LED(int(LEDcommands[line][1]),int(LEDcommands[line][2]),int(LEDcommands[line][3]),int(LEDcommands[line][4]))
            time.sleep(2.0)
        if line < len(LEDcommands):								              # This line needed for timing reasons when an LED sequence is removed
          if (LEDcommands[line][0] == "off"):                   # If off command encountered then turn off all the LEDs
            off_LED()
    q.put(SolidLastLEDcmds)                                     # Put SolidLastLEDcmds on the queue from the spawned thread   


def shutdown():                                                 # Fairly useless right now, add future functionality to shutdown the system
  try:
    os.remove('stockalert.wav')                                 # Cleanup / remove old .wav files
  except OSError:
    pass 
  off_LED()
  t.cancel()
  exit()

if __name__ == "__main__":
    off_LED()
    threads = []                                                # <-- Main initialization start
    LEDcommands = []                                            #
    SolidLastLEDcmds = []                                       #
    t = None                                                    #
    t2 = None                                                   #
    q = queue.Queue()                                           # 
    calendar_alert = False                                      #
    active_weather_alert = False                                #
    last_weather_alert = False                                  # <-- Main initialization end
    try:
      national_weather_service = WeatherAlerts(samecodes=MY_SAME_CODE) # An Error is generated first time WeatherAlerts module is run after 1st boot 
    except:                                                     # Trap the error and do nothing
      pass
    nws = WeatherAlerts(samecodes=MY_SAME_CODE, cachetime=3)    # Check for weather alerts and update the feed every 3 minutes
    os.system('clear')                                          # Clear the terminal screen
    print('Starting AlertTube...')
    fetch_timer(nws)                                            # Run immediately and then every CHECK_DELAY seconds to see if there is an alert  
    see_alerts = True
    f4, f23, f24 = setup_and_register_interrupts()
    events, f4, f23, f24 = read_GPIO(f4, f23, f24)              # 1st time read GPIO states and do nothing, since no buttons pushed
    while True:
      events, f4, f23, f24 = read_GPIO(f4, f23, f24)            # Read GPIO states
      try: 
        for fileno, event in events:
          if fileno == f4.fileno() and aplay_not_active():      # If button 3 pushed and not playing a wav file
            play_tomorrows_forecast(nws)  
          elif fileno == f23.fileno():                          # If button 1 pushed         
            os.system('aplay confirm.wav > /dev/null 2>&1 &')   # Play confirm click in background and trash text
            see_alerts = not(see_alerts)                        # Toggle see_alerts state
            f25 = open('/sys/class/gpio/gpio25/' + 'value', 'w')
            if see_alerts == False:
              f25.write('1')                                    # LED active low, so if alerts=False then LED off 
            else:
              f25.write('0')
              SolidLastLEDcmds = []                             # Reset so solid LEDs will come back after alerts are enabled
            f25.close()
            time.sleep(0.5)
          elif fileno == f24.fileno() and aplay_not_active():   # If button 2 pushed and not playing a wav file
            play_todays_forecast(nws)  
        if see_alerts == True:                                  # If see_alerts is enabled then...
          t2 = Thread(target=display_events,args=(LEDcommands, SolidLastLEDcmds)) # run thread to display the LED sequence
          if threading.active_count() <= 2:                     # If there are 2 or less threads running then start the RGB LED display_events thread
            t2.start()                                          # Run display_events as a separate thread, so it doesn't slow down button responsivness
          try:
            SolidLastLEDcmds = q.get_nowait()                   # Get the last set of SolidLEDcmds from the queue and save them           
          except:
            pass  
        else:
          off_LED()
      except KeyboardInterrupt:                                 # If <CTRL>-<C> hit then turn off the LEDs, cancel any threads and exit
        a = Thread(target=shutdown)
        a.start()
        a.join()

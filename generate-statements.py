#!/usr/bin/env python3

###RELEASE DETAIL: This program is designed to give a detailed summary for the utility bill usages and estimated costs, broken down into usage amounts per company.  
###LAST UPDATED: December 13, 2024

###NOTABLES: Fixed issues for summertime months by doing a different way of calculating in the summer months, or when the gas usages are super low

###IMPORTANT: Need to get the existing company proprietary portion built in and figure the detail on porting the information to the system with a procedure pulling it from the BAS machine.  In a perfect world, I'll get Linux to do this as well....

###LOCATIONS: Gas - 300
###LOCATIONS: Gas:Bill - 541
###LOCATIONS: Gas:Variance - 608
###LOCATIONS: Electricity - 744
###LOCATIONS: Electricity:Bill - 1046
###LOCATIONS: Electricity:Variance - 1109
###LOCATIONS: Electricity:Report (qreport) - 2049 
###LOCATIONS: Water - 2115
###LOCATIONS: Water:Bill - 2474
###LOCATIONS: Water:Variance - 2598

import psycopg2, psycopg2.extras, os, sys, datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import datetime
from datetime import timedelta
from dateutil.relativedelta import relativedelta
import time
from decimal import Decimal
from fpdf import FPDF
import json

YR = '29'
gj_conv = 0.001055
mm_conv = 0.1055  #(10CF)
#gj_conv = 1

STORE1_FOOTAGE = 2222
STORE2_FOOTAGE = 5555
FC_FOOTAGE = 9000
TENANT_GAS_USERS = STORE1_FOOTAGE + STORE2_FOOTAGE + FC_FOOTAGE
ET_FOOTAGE = 1000000 - TENANT_GAS_USERS
WT_FOOTAGE = 900000
PARKADE_FOOTAGE = 600000

OVERALL_FOOTAGE = TENANT_GAS_USERS + ET_FOOTAGE + WT_FOOTAGE + PARKADE_FOOTAGE

curr = datetime.datetime.now()
ytd_curr_date = datetime.datetime.now().date()
ytd_end_date = ytd_curr_date + relativedelta(months=-2)
curr_month = ytd_end_date.strftime("%m")
curr_month_num = ytd_end_date.month
curr_yr = curr.year
curr_p = curr.strftime("%b %d, %Y")
curr_print = "Generated on: %s" % curr_p

class Reading:
    def __init__(self, ryear, rmonth, rlocation, rvalue, rcost):
        self.ryear = ryear
        self.rmonth = rmonth
        self.rlocation = rlocation
        self.rvalue = rvalue
        self.rcost = rcost

read_list = []

def jdefault(o):
    return o.__dict__

##Below is the procedure / function that sends the email containing the generated PDF statement
def send_it(file_to_send):
    ##If no recipient email is provided, fail and exit
    my_email = input("Give me your email address (or enter 'STOP' to skip the email component): "
    if my_email == "STOP":
        sys.exit(1)
    else:
        ##Insert company-specific email server detail below
        SERVER = "smtp.server.com"
        FROM = "special.user@domain.com"
        TO = ['special.user@domain.com', my_email]
        SUBJECT = "Utility Report"

        msg = MIMEMultipart('alternative')
        msg['Subject'] = SUBJECT
        msg['From'] = FROM
        msg['To'] = ','.join(TO)

        html = "<html><head><title>Utility Info</title></head>"
        html += "<body>Attached is the utility file you're looking for</body></html>"

        text = "Attached is the utility information you requested"

        part1 = MIMEText(text, 'plain')
        part2 = MIMEText(html, 'html')

        msg.attach(part1)
        msg.attach(part2)

        attmt = open(file_to_send, "rb")
        t = MIMEBase('application', 'octet-stream')
        t.set_payload(attmt.read())
        encoders.encode_base64(t)
        #filenm = file_to_send
        filenm = sys.argv[1] + sys.argv[2] + "-" + utility_type + ".pdf"
        t.add_header('Content-Disposition', "attachment; filename= %s" % filenm)
        msg.attach(t)
        
        server = smtplib.SMTP(SERVER)
        server.sendmail(FROM, TO, msg.as_string())
        server.quit()


##Checking for the four input variables needed (Month name, 4 digit year, utility type information desired (gas, electricity, or water), and the report type (bill or variance)
if len(sys.argv) < 4:
    print ("This program is written to take four input variables: month (the month name, not the number), the year(4 digits), a utility type (gas, electricity, or water), and the report type desired (bill or variance).  Please try again including these details at the command line prompt.")
    sys.exit(1)

##Checking to ensure that a valid month entry (or ytd - Year To Date, or q1-q4 - a quarter of the year) has been given to the script
try:
    monthname = sys.argv[1].lower()
except IndexError:
    print ("You didn't give me a month to get information for.  Either give a month name or ytd or q1-q4")
    sys.exit(1)

##Checks for a year number, and verifies if it is in 4 digit format
try: 
    yearno = sys.argv[2]
except IndexError:
    print ("You didn't give me a year to search for this data.  It should be in 4 digit format")

if len(yearno) != 4:
    print ("The year should be a four digit number.  Please retry")
    sys.exit(1)

##Tuple of tuples containing the digits corresponding with the months of the year and other identifiers that may be given by a user
MONTHS = (
        ('01', 'january'),
        ('02', 'february'),
        ('03', 'march'),
        ('04', 'april'),
        ('05', 'may'),
        ('06', 'june'),
        ('07', 'july'),
        ('08', 'august'),
        ('09', 'september'),
        ('10', 'october'),
        ('11', 'november'),
        ('12', 'december'),
        ('13', 'q1'),
        ('14', 'q2'),
        ('15', 'q3'),
        ('16', 'q4'),
        ('17', 'ytd'),
)


##Tuple of tuples containing the amounts corresponding with the contract usage amounts estimated for each month
##The notes next to it are the old values from a past contract
CONTRACT_AMOUNTS = (
        ('january', 1500000),  #2300000
        ('february', 1550000),  #2100000
        ('march', 1500000),  #2300000
        ('april', 1520000),  #2300000
        ('may', 1590000),  #2500000
        ('june', 1510000),  #2500000
        ('july', 1550000),  #2700000
        ('august', 1500000),  #2500000
        ('september', 1600000),  #2400000
        ('october', 1600000),  #2300000
        ('november', 15000000),  #2100000
        ('december', 1400000),  #2100000
)


##Lambda function to pull needed information from above tuples
DATENO = list(filter(lambda x: x[1] == monthname, MONTHS))
resultant = int(DATENO[0][0])
monthname2a = monthname
s_month_name = monthname
month_group = []
months_count = 1
qreport = False
##Definitions for quarters (if given), or year-to-date
if resultant > 12:
    if resultant == 13:
        month_group = ['01', '02', '03']
        print (month_group)
        months_count = 3
        qreport = True
    elif resultant == 14:
        month_group = ['04', '05', '06']
        print (month_group)
        months_count = 3
        qreport = True
    elif resultant == 15:
        month_group = ['06', '07', '08']
        print (month_group)
        months_count = 3
        qreport = True
    elif resultant == 16:
        month_group = ['10', '11', '12']
        print (month_group)
        months_count = 3
        qreport = True
    elif resultant == 17:
        qreport = True
        if int(yearno) < int(curr_yr):
            month_group = ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12']
            months_count = 12
        else:
            months_count = 0
            for m1 in MONTHS:
                if int(m1[0]) <= curr_month_num:
                    print (m1[0])
                    months_count +=1
                    month_group.append(m1[0])

else:
    DATENUM = DATENO[0][0]
    print (DATENUM)
    month_group.append(DATENUM)

addyr = int(YR) + 1

##Checking for the type of data being requested.  If not found, it will fail and exit with an explanation
try: 
    utility_type = sys.argv[3].lower()
except IndexError:
    print ("You didn't give me a utility type to generate the accounting data for.  The choices are gas, electricity, or water.")
    sys.exit(1)

##Checking to ensure a report type has been indicated (either a bill report or variance - year over year - report
try:
    report_type = sys.argv[4].lower()
except IndexError:
    print ("You didn't give me a report type to generate.  The choices are bill or variance.")
    sys.exit(1)

try:
    conn = psycopg2.connect("dbname='infodb' host='localhost' user='dbuser' password='xxxxxxxx'")
except:
    print("I cannot connect to the database")
    sys.exit()

theader2 =  "Multi-month Usage Summary"
if qreport:
    tgt_file2 = monthname + "-" + yearno + "-" + utility_type + "variance_report.pdf"
    pdf1 = FPDF()
    pdf1.add_page()
    pdf1.set_font("Times", 'B', 24) 
    cell_width = (len(theader2) * 4.3) + 20
    #hwidth = cell_width * 2
    pdf1.cell(cell_width, 40, theader2, ln=1)
    pdf1.set_font("Times", 'U', 14) 
    pdf1.cell(70, 10, "")
    pdf1.cell(40, 10, "Tower One")
    pdf1.cell(40, 10, "Tower Two")
    pdf1.cell(40, 10, "Parkade", ln=1)
    pdf1.cell(70, 10, "")
    pdf1.cell(40, 10, "Usage: Cost")
    pdf1.cell(40, 10, "Usage: Cost")
    pdf1.cell(40, 10, "Usage: Cost", ln=1)

if len(month_group) > 1:
    print ("We've got a winner")
    multiples = 1
else:
    print ("It's just a single request")
    multiples = 0


###This is the counter to see if we're done going through the months before we try to generate a report from the library of collected information
testctr = 0

for p in month_group:
    testctr += 1
    start_month = int(p)
    s_month_name = list(filter(lambda z: z[0] == p, MONTHS))
    start_date = datetime.datetime.strptime(yearno + p + "01", "%Y%m%d").date()
    monthname2 = list(filter(lambda x: x[0] == p, MONTHS))
    monthname2a = monthname2[0][1]
    end_date = start_date + relativedelta(months=+1)

    prev_date = start_date + relativedelta(months=-1)
    two_prev_date = start_date + relativedelta(months=-2)
    three_prev_date = start_date + relativedelta(months=-3)
    prev_yr = start_date + relativedelta(years=-1)
    two_prev_yr = start_date + relativedelta(years=-2)

    scan_start = two_prev_date.month
    prev_month = prev_date.month
    head_mo = end_date.month
    if head_mo == 1:
        head_mo = 13

    lastyear = int(yearno) - 1

    ##Start with gas utility requests
    if utility_type == 'gas':
        request_type = 'Gas'
        main_gas = []
        wt_gas = []
        et_gas = []
        print ("You want the gas data")
        #print start_month
        #print yearno
        #time.sleep(10)
        cur = conn.cursor()
        cur.execute("""SELECT tracking_reading.meter_id, usage_amount, usage_cost, transmission_cost, month FROM tracking_reading, tracking_meter WHERE tracking_reading.meter_id=tracking_meter.id AND tracking_meter.mstype = 'Monthly' AND tracking_meter.mtype = '%s' AND tracking_reading.month = '%s' AND tracking_reading.year = '%s'""" % (request_type, start_month, yearno))  #AND recorded >= '%s' AND recorded <= '%s' """  % (start_date, end_date))
        #cur.execute("""SELECT tracking_reading.meter_id, usage_amount, usage_cost, transmission_cost, month FROM tracking_reading, tracking_meter WHERE tracking_reading.meter_id=tracking_meter.id AND tracking_meter.mstype = 'Monthly' AND tracking_meter.mtype = '%s' AND tracking_reading.month > '%s' AND tracking_reading.month < '%s' AND tracking_reading.year = '%s'""" % (request_type, scan_start, head_mo, yearno))  #AND recorded >= '%s' AND recorded <= '%s' """  % (start_date, end_date))
        rows = cur.fetchall()
        if rows:
            #print rows
            for row in rows:
                if row[0] == 1:
                    transmission_cost = row[3]
                    usage_cost = row[2]
                    usage_amount = row[1]
                    #trans_cost_per_foot = transmission_cost/1935509
                    trans_cost_per_foot = transmission_cost/2520848  ###This is the total footages of first tower, second tower and parkade
                    total_cost = usage_cost + transmission_cost
                    cost_per_unit = total_cost / usage_amount
                    corr_cost_per_unit = usage_cost / usage_amount
                    print ("The year is %s" % yearno)
                    print ("The total cost of the bill is %f" % total_cost)
                    print ("The total usage for the month was %d" % usage_amount)
                    print ("The cost per square foot for transmission is $%.5f" % trans_cost_per_foot)
                    print ("The old cost per unit was $%.5f" % cost_per_unit)
                    print ("The corrected cost per unit is $%.5f" % corr_cost_per_unit)
                    print ("############################################################################")
                    print ("\n")
                elif row[0] == 19: 
                    store2_gas_current = row[1]
                elif row[0] == 20:
                    amenity_heating_current = row[1]
                elif row[0] == 21: 
                    amenity_hot_water_current = row[1]
                elif row[0] == 18:
                    store1_gas_current = row[1]
        else:
            print ("We probably need to estimate this value, as I don't have anything right now for the given month and year - Part One")
            ###This is not working for December, probably because it cannot negotiate a year change and reversion back to January in its currently programmed state.  I'll talk to the programmer about this issue.  :-)
            ###Need to program in a way to estimate based on the last two years' data
            sys.exit(1)
        
        if start_month == 1:
            lastmyeari = int(yearno) - 1
            lastmyear = str(lastmyeari)
        else:
            lastmyear = yearno
        curr1 = conn.cursor()
        curr1.execute("""SELECT tracking_reading.meter_id, usage_amount, usage_cost, transmission_cost, month FROM tracking_reading, tracking_meter WHERE tracking_reading.meter_id=tracking_meter.id AND tracking_meter.mstype = 'Monthly' AND tracking_meter.mtype = '%s' AND tracking_reading.month = '%s' AND tracking_reading.year = '%s'""" % (request_type, prev_month, lastmyear))  #AND recorded >= '%s' AND recorded <= '%s' """  % (start_date, end_date))
        rows2 = curr1.fetchall()
        if rows2:
            print (rows2)
            for row2 in rows2:
                if row2[0] == 1:
                    p_transmission_cost = row2[3]
                    p_usage_cost = row2[2]
                    p_usage_amount = row2[1]
                    p_trans_cost_per_foot = p_transmission_cost/2530000  ###This is the total footages of first tower, second tower and parkade
                    p_total_cost = p_usage_cost + p_transmission_cost
                    p_cost_per_unit = p_total_cost / p_usage_amount
                    corr_cost_per_unit = p_usage_cost / p_usage_amount
                elif row2[0] == 19: 
                    store2_gas_past = row2[1]
                elif row2[0] == 20:
                    amenity_heating_past = row2[1]
                elif row2[0] == 21: 
                    amenity_hot_water_past = row2[1]
                elif row2[0] == 18:
                    store1_gas_past = row2[1]
        else:
            print ("We probably need to estimate this value, as I don't have anything right now for the given month and year - Part Two-New")
            sys.exit(1)


        try:
            store1_gas_current 
        except NameError:
            print ("I don't have Store4's current usage")
            sys.exit(1)
        try:
            store1_gas_past
        except NameError:
            print ("I don't have Store4's past usage")
            sys.exit(1)
        store1_usage = ((store1_gas_current - store1_gas_past) * 5)/947.82
        print ("Store4 usage - %.2f" % store1_usage)
        if store2_gas_current and store2_gas_past:
            store2_usage = ((store2_gas_current - store2_gas_past) * 5)/947.82  ##One MJ = 947.82 BTU
            print ("store2 usage - %.2f" % store2_usage)
        else:
            print ("I do not have all the Store2 information")
        if amenity_hot_water_current and amenity_hot_water_past:
            fc_hot_water_usage = (amenity_hot_water_current - amenity_hot_water_past) * 0.0373  ##Converts m3 to GJ
            print ("Amenity Space hot water usage - %.2f" % fc_hot_water_usage)
        else:
            print ("I do not have all the amenity hot water information")
        if amenity_heating_current and amenity_heating_past:
            fc_heating_usage = ((amenity_heating_current - amenity_heating_past) * 10000) * 0.00000105587
            print ("Amenity Space heat usage - %.2f" % fc_heating_usage)
        else:
            print ("I do not have all the amenity heating information")


        ##################Was commented out below here
        ##To address the end of year scenarios, with incrementing the year and changing the month to january
        if start_month == 1:
            prev_month = 12
            newyrstring = int(yearno) - 1
        else:
            prev_month = start_month - 1
            newyrstring = yearno
        ########################Was commented out above here

        print ("###########################################################################")
        print ("\n")

        start_date = datetime.datetime.strptime(yearno + p + "01", "%Y%m%d").date()
        print ("%s is the start date" % (start_date))
        end_date = start_date + relativedelta(months=+1)
        print(end_date)

        curr3 = conn.cursor()
        curr3.execute("""SELECT tracking_reading.meter_id, usage_amount, description, recorded FROM tracking_reading, tracking_meter WHERE tracking_reading.meter_id=tracking_meter.id AND tracking_meter.mtype = 'Gas' AND month = '%s' AND year = '%s' """  % (start_month, yearno))
        rows3 = curr3.fetchall()
        if rows3:
            for row3 in rows3:
                if row3[0] == 22:
                    main_gas.append(row3[1])
                elif row3[0] == 23:
                    wt_gas.append(row3[1])
                elif row3[0] == 24:
                    et_gas.append(row3[1])
                else:
                    pass

        main_gas.sort()
        wt_gas.sort()
        et_gas.sort()

        ##The following gets the usage, but should be able to be put into a subroutine or function
        mg_last_val = main_gas[-1]
        mg_first_val = main_gas[0]
        mg_usage = (mg_last_val - mg_first_val) * mm_conv
        print ("The gas usage for the month of %s was %d" % (monthname2a, mg_usage))

        etg_last_val = et_gas[-1]
        etg_first_val = et_gas[0]
        etg_usage = ((etg_last_val - etg_first_val) * 100) * gj_conv
        etg_readings = len(et_gas)
        print ("We have %d entries for the month of %s" % (etg_readings, monthname2a))
        print ("The first tower gas usage for the month of %s was %d" % (monthname2a, etg_usage))

        wtg_last_val = wt_gas[-1]
        wtg_first_val = wt_gas[0]
        wtg_usage = ((wtg_last_val - wtg_first_val) * 100) * gj_conv
        wtg_readings = len(wt_gas)
        print ("We have %d entries for the month of %s" % (wtg_readings, monthname2a))
        print ("The second tower gas usage for the month of %s was %d" % (monthname2a, wtg_usage))
        print ("\n")

        fc_total_usage = fc_heating_usage + fc_hot_water_usage
        summed_usage = fc_heating_usage + etg_usage + wtg_usage + heat_usage + store1_usage
        adjusted_sum_use = fc_heating_usage + store2_usage + store1_usage
        if summed_usage < 0:
            summed_usage = 0
        parkade_usage = usage_amount - summed_usage
        if parkade_usage < 0:
            print ("The parkade usage was below zero, meaning that our meters show more usage than the bill shows")
            ###The below will give the remainder amount after the tenant meters
            remainder_use = usage_amount - adjusted_sum_use
            total_phantom_use = etg_usage + wtg_usage
            et_pct = etg_usage / total_phantom_use
            wt_pct = 1.0 - et_pct
            ett_use = remainder_use * et_pct
            wtt_use = remainder_use - ett_use
            store1_usage_calc = (Decimal(store1_usage) / Decimal(summed_usage)) * usage_cost
            store2_usage_calc =  (Decimal(store2_usage) / Decimal(summed_usage)) * usage_cost
            fc_usage_calc = (Decimal(fc_total_usage) / Decimal(summed_usage)) * usage_cost
            et_usage_calc = ((Decimal(etg_usage) - Decimal(fc_hot_water_usage)) / Decimal(summed_usage)) * usage_cost
            wt_usage_calc = (Decimal(wtg_usage) / Decimal(summed_usage)) * usage_cost
            partial_sum_cost = store1_usage_calc + store2_usage_calc + fc_usage_calc + et_usage_calc + wt_usage_calc
            parkade_usage_calc = usage_cost - partial_sum_cost
            parkade_usage = 0
        else:
            ett_use = etg_usage - fc_hot_water_usage
            wtt_use = wtg_usage
            store1_usage_calc = (Decimal(store1_usage) * corr_cost_per_unit)
            store2_usage_calc =  (Decimal(store2_usage) * corr_cost_per_unit)
            fc_usage_calc = (Decimal(fc_total_usage) * corr_cost_per_unit)
            et_usage_calc = ((Decimal(etg_usage) - Decimal(fc_hot_water_usage)) * corr_cost_per_unit)
            wt_usage_calc = (Decimal(wtg_usage) * corr_cost_per_unit)
            partial_sum_cost = store1_usage_calc + store2_usage_calc + fc_usage_calc + et_usage_calc + wt_usage_calc
            parkade_usage_calc = usage_cost - partial_sum_cost
        parkade_et_use = Decimal(parkade_usage) * Decimal(0.565)
        parkade_wt_use = Decimal(parkade_usage) - parkade_et_use
        fc_et_use = Decimal(fc_total_usage) * Decimal(0.565)
        fc_wt_use = Decimal(fc_total_usage) - fc_et_use
        etga_usage = ett_use
        wtga_usage = wtt_use

        ###Get transmission costs by multiplying the footage of the space by the transmission cost per square foot
        ###Then add already calculated usage costs
        ###The parkade absorbs the difference, if any
        store1_t_cost = (STORE1_FOOTAGE * trans_cost_per_foot)
        store1_cost = store1_usage_calc + store1_t_cost
        store2_t_cost = (STORE2_FOOTAGE * trans_cost_per_foot)
        store2_cost = store2_usage_calc + store2_t_cost
        fc_t_cost = (FC_FOOTAGE * trans_cost_per_foot) 
        fc_cost = fc_usage_calc + fc_t_cost
        fc_et = fc_cost * Decimal(0.565)
        fc_wt = fc_cost - fc_et
        et_t_cost = (ET_FOOTAGE * trans_cost_per_foot)
        et_cost = et_usage_calc + et_t_cost
        wt_t_cost = (WT_FOOTAGE * trans_cost_per_foot)
        wt_cost = wt_usage_calc + wt_t_cost
        parkade_t_cost = (PARKADE_FOOTAGE * trans_cost_per_foot)
        parkade_cost = parkade_usage_calc + parkade_t_cost
        park_et = parkade_cost * Decimal(0.565)
        park_wt = parkade_cost - park_et
        total_t_cost = store1_t_cost + store2_t_cost + fc_t_cost + et_t_cost + wt_t_cost + parkade_t_cost


        header = utility_type[:1].upper() + utility_type[1:]
        moname = monthname[:1].upper() + monthname[1:]
        theader = moname + " " + yearno + " " + header + " Bill Allocation"
        tgt_file = monthname + "-" + yearno + "-" + utility_type + ".pdf"
        second_tower_account = "rbt2.ga001"
        first_tower_account = "rbt1.ga001"
        first_amenity_center_account = "rbt1.68020"
        second_amenity_center_account = "rbt2.68020"
        first_parkade_account = "rbt1.ga001"
        second_parkade_account = "rbt2.ga001"
        gst_account = "gs001.001"


        if report_type == 'bill':
            gst_value = input("Please give the dollar amount (with no dollar signs) of the GST for the entire bill :")
            if gst_value is None:
                print("I really need a GST dollar value to continue")
                sys.exit(1)
            else:
                print("Thank you!")
                gst_true = Decimal(gst_value)
                new_tot_cost = total_cost + gst_true

            if multiples == 0:
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Arial", 'B', 24) 
                cell_width = (len(theader) * 4.3) + 20
                pdf.cell(cell_width, 20, theader, ln=1, align="C")
                pdf.set_font("Times", size=10) 
                pdf.cell(cell_width, 10, curr_print, ln=1, align="C")
                pdf.set_font("Times", 'U', 14) 
                pdf.cell(70, 10, "Entity")
                pdf.cell(40, 10, "Account Number")
                pdf.cell(40, 10, "Usage Volume")
                pdf.cell(40, 10, "Cost Incurred", ln=1)
                pdf.set_font("Times", size=14) 
                pdf.cell(70, 10, "Store4 Costs")
                pdf.cell(40, 10, first_tower_account)
                pdf.cell(40, 10, '{:,.0f}'.format(store1_usage), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(store1_cost), ln=1)
                pdf.cell(70, 10, "Store2 Costs")
                pdf.cell(40, 10, first_tower_account)
                pdf.cell(40, 10, '{:,.0f}'.format(store2_usage), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(store2_cost), ln=1)
                pdf.cell(70, 10, "Tower One Parkade Costs")
                pdf.cell(40, 10, first_parkade_account)
                pdf.cell(40, 10, '{:,.0f}'.format(parkade_et_use), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(park_et), ln=1)
                pdf.cell(70, 10, "Tower Two Parkade Costs")
                pdf.cell(40, 10, second_parkade_account)
                pdf.cell(40, 10, '{:,.0f}'.format(parkade_wt_use), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(park_wt), ln=1)
                pdf.cell(70, 10, "Tower One Fitness Ctr Costs")
                pdf.cell(40, 10, first_amenity_center_account)
                pdf.cell(40, 10, '{:,.0f}'.format(fc_et_use), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(fc_et), ln=1)
                pdf.cell(70, 10, "Tower Two Fitness Ctr Costs")
                pdf.cell(40, 10, second_amenity_center_account)
                pdf.cell(40, 10, '{:,.0f}'.format(fc_wt_use), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(fc_wt), ln=1)
                pdf.cell(70, 10, "Tower One Costs")
                pdf.cell(40, 10, first_tower_account)
                pdf.cell(40, 10, '{:,.0f}'.format(etga_usage), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(et_cost), ln=1)
                pdf.cell(70, 10, "Tower Two Costs")
                pdf.cell(40, 10, second_tower_account)
                pdf.cell(40, 10, '{:,.0f}'.format(wtga_usage), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(wt_cost), ln=1)
                pdf.cell(110, 10, "Subtotals", border="T")
                pdf.cell(40, 10, '{:,.0f}'.format(usage_amount), border="T", align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(total_cost), border="T", ln=1)
                pdf.cell(70, 10, "GST")
                pdf.cell(80, 10, gst_account)
                pdf.cell(40, 10, '${:,.2f}'.format(gst_true), ln=1)
                pdf.cell(110, 10, "Totals", border="T")
                pdf.cell(40, 10, '{:,.0f}'.format(usage_amount), border="T", align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(new_tot_cost), border="T")
                pdf.output(tgt_file)

        elif report_type == 'variance':
            if scan_start >= 11:
                scan_start = 0
            else:
                scan_start += 1
            cur.execute("""SELECT tracking_reading.meter_id, usage_amount, usage_cost, transmission_cost, month FROM tracking_reading, tracking_meter WHERE tracking_reading.meter_id=tracking_meter.id AND tracking_meter.mstype = 'Monthly' AND tracking_meter.mtype = '%s' AND tracking_reading.month = '%s' AND tracking_reading.year = '%s'""" % (request_type, start_month, lastyear))  #AND recorded >= '%s' AND recorded <= '%s' """  % (start_date, end_date))
            rows = cur.fetchall()
            print (request_type)
            print (scan_start)
            print (head_mo)
            print (lastyear)
            if rows:
                for row in rows:
                    if row[0] == 1 and row[4] == start_month:
                        l_transmission_cost = row[3]
                        l_usage_cost = row[2]
                        l_usage_amount = row[1]
                        l_total_cost = l_usage_cost + l_transmission_cost
                        l_cost_per_unit = l_total_cost / l_usage_amount
                        print ("############################################################################")
                        print ("\nLAST YEAR'S DATA\n")
                        print ("The total cost of last year's bill was %f" % l_total_cost)
                        print ("The total usage for the same month last year was %d" % l_usage_amount)
                        print ("The cost per unit last year was $%.5f" % l_cost_per_unit)
                        print ("############################################################################")
                        print ("\n")


            l_et_gas = []
            l_wt_gas = []
            l_main_gas = []
            curr23 = conn.cursor()
            curr23.execute("""SELECT tracking_reading.meter_id, usage_amount, description, recorded FROM tracking_reading, tracking_meter WHERE tracking_reading.meter_id=tracking_meter.id AND tracking_meter.mstype = 'Daily' AND tracking_meter.mtype = '%s' AND tracking_reading.month = '%s' AND tracking_reading.year = '%s'""" % (request_type, start_month, lastyear))  #AND recorded >= '%s' AND recorded <= '%s' """  % (start_date, end_date))
            rows23 = curr23.fetchall()
            if rows23:
                for row23 in rows23:
                    if row23[0] == 22:
                        l_main_gas.append(row23[1])
                    elif row23[0] == 23:
                        l_wt_gas.append(row23[1])
                    elif row23[0] == 24:
                        l_et_gas.append(row23[1])
                    else:
                        pass
            else: 
                print ("The previous year does not have an entry, so I'm kind of stuck")

            l_main_gas.sort()
            l_wt_gas.sort()
            l_et_gas.sort()

            ##The following gets the usage, but should be able to be put into a subroutine or function
            l_mg_last_val = l_main_gas[-1]
            l_mg_first_val = l_main_gas[0]
            l_mg_usage = (l_mg_last_val - l_mg_first_val) * mm_conv
            print ("The gas usage for the month of %s was %d" % (monthname2a, l_mg_usage))

            l_etg_last_val = l_et_gas[-1]
            print(l_etg_last_val)
            l_etg_first_val = l_et_gas[0]
            print(l_etg_first_val)
            l_etg_usage = ((l_etg_last_val - l_etg_first_val) * 100) * gj_conv
            l_etg_readings = len(l_et_gas)
            print ("We have %d entries for the month of %s" % (l_etg_readings, monthname2a))
            print ("The first tower gas usage for the month of %s was %d" % (monthname2a, l_etg_usage))

            l_wtg_last_val = l_wt_gas[-1]
            l_wtg_first_val = l_wt_gas[0]
            l_wtg_usage = ((l_wtg_last_val - l_wtg_first_val) * 100) * gj_conv
            l_wtg_readings = len(l_wt_gas)
            print ("We have %d entries for the month of %s" % (l_wtg_readings, monthname2a))
            print ("The second tower gas usage for the month of %s was %d" % (monthname2a, l_wtg_usage))
            print ("\n")
            #time.sleep(30)
            cur41 = conn.cursor()
            cur41.execute("""SELECT id, detail, meter_affected_id FROM eap_tracker_energyvariance WHERE monthly_utility_explanation = 't' AND meter_affected_id = 1 AND month = '%s' AND year = '%s'""" % (start_month, yearno))
            rows41 = cur41.fetchall()
            if rows41:
                for row41 in rows41:
                    gvariance = row41[1]
            else:
                gvariance = "No explanation given"

            g_tower_usage = etg_usage + wtg_usage
            pk_usage = usage_amount - g_tower_usage
            gl_tower_usage = l_etg_usage + l_wtg_usage
            plk_usage = l_usage_amount - gl_tower_usage

            tgt_file = monthname + "-" + yearno + "-" + utility_type + "_variance_report.pdf"
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Times", 'B', 24) 
            cell_width = (len(theader) * 4.3) + 20
            pdf.cell(cell_width, 40, theader, ln=1)
            pdf.cell(120, 10, "Year Over Year Comparison", ln=1)
            pdf.set_font("Times", 'U', 14) 
            pdf.cell(70, 10, "Meter Coverage")
            pdf.cell(40, 10, "Current Usage")
            pdf.cell(40, 10, "Last Year")
            pdf.cell(40, 10, "Percent Increase", ln=1)
            pdf.set_font("Times", size=14) 
            pdf.cell(70, 10, "Entire Tower Gas - Billed Usage")
            pdf.cell(40, 10, '{:,.0f}'.format(usage_amount), align="C")
            pdf.cell(40, 10, '{:,.0f}'.format(l_usage_amount), align="C")
            guse_pct_increase = ((usage_amount - l_usage_amount)/l_usage_amount)*100
            pdf.cell(40, 10, '{:,.2f}%'.format(guse_pct_increase), ln=1)
            pdf.set_fill_color(240,240,240)
            pdf.cell(70, 10, "Entire Tower Gas Metering", fill=True)
            pdf.cell(40, 10, '{:,.0f}'.format(mg_usage), align="C", fill=True)
            pdf.cell(40, 10, '{:,.0f}'.format(l_mg_usage), align="C", fill=True)
            muse_pct_increase = ((mg_usage - l_mg_usage)/l_mg_usage)*100
            pdf.cell(40, 10, '{:,.2f}%'.format(muse_pct_increase), fill=True, ln=1)
            pdf.cell(70, 10, "Tower One")
            pdf.cell(40, 10, '{:,.0f}'.format(etg_usage), align="C")
            pdf.cell(40, 10, '{:,.0f}'.format(l_etg_usage), align="C")
            etg_pct_increase = ((float(etg_usage)-float(l_etg_usage))/float(l_etg_usage))*100
            pdf.cell(40, 10, '{:,.2f}%'.format(etg_pct_increase), ln=1)
            pdf.set_fill_color(240,240,240)
            pdf.cell(70, 10, "Tower Two", fill=True)
            pdf.cell(40, 10, '{:,.0f}'.format(wtg_usage), align="C", fill=True)
            pdf.cell(40, 10, '{:,.0f}'.format(l_wtg_usage), align="C", fill=True)
            if l_wtg_usage == 0:
                wtg_pct_increase = 100.00
            else:
                wtg_pct_increase = ((float(wtg_usage)-float(l_wtg_usage))/float(l_wtg_usage))*100 
            pdf.cell(40, 10, '{:,.2f}%'.format(wtg_pct_increase), fill=True, ln=1)
            pdf.cell(70, 10, "Other Usages")
            pdf.cell(40, 10, '{:,.0f}'.format(pk_usage), align="C")
            pdf.cell(40, 10, '{:,.0f}'.format(plk_usage), align="C")
            plk_pct_increase = ((float(pk_usage)-float(plk_usage))/float(plk_usage))*100
            pdf.cell(40, 10, '{:,.2f}%'.format(plk_pct_increase), ln=1)
            pdf.cell(180, 10, "Variance Notes:", fill=True, ln=1)
            pdf.cell(180, 10, gvariance, ln=1)
            pdf.output(tgt_file)
            

    elif utility_type == 'electricity':
        print ("You want electricity data")
        electric_cost = []
        et_elec_cost = []
        wt_elec_cost = []
        electric_usage = []
        et_elec_usage = []
        wt_elec_usage = []
        trans_cost = []
        et_trans_cost = []
        wt_trans_cost = []
        total_sum = []
        total_for_contract = []
        text2 = "Missing Tower One 4-17 readingsi\n"
        text3 = "Missing Tower One 18-29 readings\n"
        text4 = "Missing Tower One 30-42 readings\n"
        text5 = "Missing Tower One 43-50 readings\n"
        text6 = "Missing Tower One 2-3 readings\n"
        text7 = "Missing Parkade readings\n"
        text8 = "Missing Tower One Fire Pump (254) readings\n"
        text9 = "Missing Tower Two 4-18 readings\n"
        text10 = "Missing Tower Two 19-31 readings\n"
        text11 = "Missing Tower Two 32-41 readings\n"
        text12 = "Missing Tower Two 2-3 readings\n"
        text13 = "Missing Tower Two fire pump readings\n"
        text14 = "Missing Tower Two fire pump readings\n"
        text15 = "Missing 205-555 8th Ave readings\n"
        text138 = "Missing Amenity Space readings\n"
        text139 = "Missing Specific Retailer readings\n"
        text140 = "Missing Tower One Fire Pump 2 readings\n"
        cur = conn.cursor()
        cur.execute("""SELECT tracking_reading.meter_id, usage_amount, usage_cost, transmission_cost FROM tracking_meter, tracking_reading WHERE tracking_meter.mtype = 'Electric' AND tracking_meter.mstype = 'Monthly' AND tracking_reading.meter_id=tracking_meter.id AND tracking_reading.month = '%s' AND tracking_reading.year = '%s'""" % (start_month, yearno))  #AND recorded >= '%s' AND recorded <= '%s' """  % (start_date, end_date))
        rows = cur.fetchall()
        if rows:
            for row in rows:
                if row[0] == 2:
                    c_4_17_ET = row[1]
                    electric_usage.append(row[1])
                    et_elec_usage.append(row[1])
                    electric_cost.append(row[2])
                    et_elec_cost.append(row[2])
                    trans_cost.append(row[3])
                    et_trans_cost.append(row[3])
                    total_sum.append(row)
                    total_for_contract.append(row[1])
                    text2 = ""
                elif row[0] == 3:
                    c_18_29_ET = row[1]
                    electric_usage.append(row[1])
                    et_elec_usage.append(row[1])
                    electric_cost.append(row[2])
                    et_elec_cost.append(row[2])
                    trans_cost.append(row[3])
                    et_trans_cost.append(row[3])
                    total_sum.append(row)
                    total_for_contract.append(row[1])
                    text3 = ""
                elif row[0] == 4:
                    c_30_42_ET = row[1]
                    electric_usage.append(row[1])
                    et_elec_usage.append(row[1])
                    electric_cost.append(row[2])
                    et_elec_cost.append(row[2])
                    trans_cost.append(row[3])
                    et_trans_cost.append(row[3])
                    total_sum.append(row)
                    total_for_contract.append(row[1])
                    text4 = ""
                elif row[0] == 5:
                    c_43_50_ET = row[1]
                    electric_usage.append(row[1])
                    et_elec_usage.append(row[1])
                    electric_cost.append(row[2])
                    et_elec_cost.append(row[2])
                    trans_cost.append(row[3])
                    et_trans_cost.append(row[3])
                    total_sum.append(row)
                    total_for_contract.append(row[1])
                    text5 = ""
                elif row[0] == 6:
                    central_plant_ET = row[1]
                    electric_usage.append(row[1])
                    et_elec_usage.append(row[1])
                    electric_cost.append(row[2])
                    et_elec_cost.append(row[2])
                    trans_cost.append(row[3])
                    et_trans_cost.append(row[3])
                    total_sum.append(row)
                    total_for_contract.append(row[1])
                    text6 = ""
                elif row[0] == 7:
                    parkade_use = row[1]
                    electric_usage.append(row[1])
                    ##Get parkade overall usage, then split to first and second portions
                    park_et_elec_usage = Decimal(parkade_use) * Decimal(0.565)
                    park_wt_elec_usage = parkade_use - park_et_elec_usage
                    ##Get parkade overall cost, then split to first and second portions
                    parkade_cost = row[2]
                    electric_cost.append(row[2])
                    park_et_elec_cost = Decimal(parkade_cost) * Decimal(0.565)
                    park_wt_elec_cost = parkade_cost - Decimal(park_et_elec_cost)
                    ##Get parkade overall transmission cost, then split to first and second portions
                    park_trans_cost = row[3]
                    park_et_trans_cost = Decimal(park_trans_cost) * Decimal(0.565)
                    park_wt_trans_cost = park_trans_cost - Decimal(park_et_trans_cost)
                    park_et_total_cost = park_et_elec_cost + park_et_trans_cost
                    park_wt_total_cost = park_wt_elec_cost + park_wt_trans_cost
                    trans_cost.append(row[3])
                    total_sum.append(row)
                    total_for_contract.append(row[1])
                    text7 = ""
                elif row[0] == 8:
                    FP_3_1_ET = row[1]
                    electric_usage.append(row[1])
                    et_elec_usage.append(row[1])
                    electric_cost.append(row[2])
                    et_elec_cost.append(row[2])
                    trans_cost.append(row[3])
                    et_trans_cost.append(row[3])
                    total_sum.append(row)
                    text8 = ""
                elif row[0] == 9:
                    c_4_18_WT = row[1]
                    electric_usage.append(row[1])
                    wt_elec_usage.append(row[1])
                    electric_cost.append(row[2])
                    wt_elec_cost.append(row[2])
                    trans_cost.append(row[3])
                    wt_trans_cost.append(row[3])
                    total_sum.append(row)
                    total_for_contract.append(row[1])
                    text9 = ""
                elif row[0] == 10:
                    c_19_31_WT = row[1]
                    electric_usage.append(row[1])
                    wt_elec_usage.append(row[1])
                    electric_cost.append(row[2])
                    wt_elec_cost.append(row[2])
                    trans_cost.append(row[3])
                    wt_trans_cost.append(row[3])
                    total_sum.append(row)
                    total_for_contract.append(row[1])
                    text10 = ""
                elif row[0] == 11:
                    c_32_41_WT = row[1]
                    electric_usage.append(row[1])
                    wt_elec_usage.append(row[1])
                    electric_cost.append(row[2])
                    wt_elec_cost.append(row[2])
                    trans_cost.append(row[3])
                    wt_trans_cost.append(row[3])
                    total_sum.append(row)
                    total_for_contract.append(row[1])
                    text11 = ""
                elif row[0] == 12:
                    central_plant_WT = row[1]
                    electric_usage.append(row[1])
                    wt_elec_usage.append(row[1])
                    electric_cost.append(row[2])
                    wt_elec_cost.append(row[2])
                    trans_cost.append(row[3])
                    wt_trans_cost.append(row[3])
                    total_sum.append(row)
                    total_for_contract.append(row[1])
                    text12 = ""
                elif row[0] == 13:
                    FP_3_1_WT = row[1]
                    electric_usage.append(row[1])
                    wt_elec_usage.append(row[1])
                    electric_cost.append(row[2])
                    wt_elec_cost.append(row[2])
                    trans_cost.append(row[3])
                    wt_trans_cost.append(row[3])
                    total_sum.append(row)
                    total_for_contract.append(row[1])
                    text13 = ""
                elif row[0] == 14:
                    FP_3_2_WT = row[1]
                    electric_usage.append(row[1])
                    wt_elec_usage.append(row[1])
                    electric_cost.append(row[2])
                    wt_elec_cost.append(row[2])
                    trans_cost.append(row[3])
                    wt_trans_cost.append(row[3])
                    total_sum.append(row)
                    total_for_contract.append(row[1])
                    text14 = ""
                elif row[0] == 15:
                    c_205_555_8th = row[1]
                    electric_usage.append(row[1])
                    et_elec_usage.append(row[1])
                    electric_cost.append(row[2])
                    et_elec_cost.append(row[2])
                    trans_cost.append(row[3])
                    et_trans_cost.append(row[3])
                    total_sum.append(row)
                    text15 = ""
                elif row[0] == 138:
                    electric_usage.append(row[1])
                    fc_elec_usage = row[1]
                    fc_et_usage = Decimal(fc_elec_usage) * Decimal(0.565)
                    fc_wt_usage = fc_elec_usage - fc_et_usage
                    electric_cost.append(row[2])
                    fc_elec_cost = row[2]
                    fc_et_cost = Decimal(fc_elec_cost) * Decimal(0.565)
                    fc_wt_cost = Decimal(fc_elec_cost) - Decimal(fc_et_cost)
                    trans_cost.append(row[3])
                    fc_trans_cost = row[3]
                    fc_et_trans_cost = Decimal(fc_trans_cost) * Decimal(0.565)
                    fc_wt_trans_cost = Decimal(fc_trans_cost) - Decimal(fc_et_trans_cost)
                    fc_et_total_cost = fc_et_cost + fc_et_trans_cost
                    fc_wt_total_cost = fc_wt_cost + fc_wt_trans_cost
                    total_sum.append(row)
                    text138 = ""
                elif row[0] == 139:
                    electric_usage.append(row[1])
                    henry_singer_usage = row[1]
                    electric_cost.append(row[2])
                    henry_singer_cost = row[2]
                    trans_cost.append(row[3])
                    henry_singer_trans_cost = row[3]
                    henry_singer_total_cost = henry_singer_trans_cost + henry_singer_cost
                    total_sum.append(row)
                    text139 = ""
                elif row[0] == 140:
                    FP_8_1_ET = row[1]
                    electric_usage.append(row[1])
                    et_elec_usage.append(row[1])
                    electric_cost.append(row[2])
                    et_elec_cost.append(row[2])
                    trans_cost.append(row[3])
                    et_trans_cost.append(row[3])
                    total_sum.append(row)
                    text140 = ""
                else:
                    pass
            final_text = text2 + text3 + text4 + text5 + text6 + text7 + text8 + text9 + text10 + text11 + text12 + text13 + text14 + text15 + text138 + text139 + text140
            print (final_text)
            print ("%s %s" % (s_month_name[0][1], yearno))
            et_elec_usage_total = sum(et_elec_usage)
            print ("The first tower usage total is %d" % et_elec_usage_total)
            et_use_per_foot = float(et_elec_usage_total) / float(ET_FOOTAGE)
            print ("The usage per square foot is %f" % et_use_per_foot)
            et_elec_cost_total = sum(et_elec_cost)
            print ("The first tower cost total is %f" % et_elec_cost_total)
            et_elec_trans_total = sum(et_trans_cost)
            print ("The first tower transmission cost total is %f" % et_elec_trans_total)
            et_grand_total = et_elec_cost_total + et_elec_trans_total
            print ("The grand total first tower cost is %f" % et_grand_total)
            et_cost_per_foot = float(et_grand_total) / float(ET_FOOTAGE)
            print ("The cost per square foot is %f" % et_cost_per_foot)
            et_cost_per_kwh = float(et_grand_total) / float(et_elec_usage_total)
            print ("The cost per kwh is %f" % et_cost_per_kwh)
            print ("*******************************************************")
            wt_elec_usage_total = sum(wt_elec_usage)
            print ("The second tower usage total is %d" % wt_elec_usage_total)
            wt_use_per_foot = float(wt_elec_usage_total) / float(WT_FOOTAGE)
            print ("The usage per square foot is %f" % wt_use_per_foot)
            wt_elec_cost_total = sum(wt_elec_cost)
            print ("The second tower cost total is %f" % wt_elec_cost_total)
            wt_elec_trans_total = sum(wt_trans_cost)
            print ("The second tower transmission cost total is %f" % wt_elec_trans_total)
            wt_grand_total = wt_elec_cost_total + wt_elec_trans_total
            print ("The grand total second tower cost is %f" % wt_grand_total)
            wt_cost_per_foot = float(wt_grand_total) / float(WT_FOOTAGE)
            print ("The cost per square foot is %f" % wt_cost_per_foot)
            wt_cost_per_kwh = float(wt_grand_total) / float(wt_elec_usage_total)
            print ("The cost per kwh is %f" % wt_cost_per_kwh)
            print ("********************************************************")
            print ("The parkade usage is %d" % parkade_use)
            print ("********************************************************")
            elec_use_sum = sum(electric_usage)
            elec_cost_sum = sum(electric_cost)
            trans_cost_sum = sum(trans_cost)
            tot_cost = elec_cost_sum + trans_cost_sum
            cost_per_unit = tot_cost / elec_use_sum
            print ("The sum of the electric usage for the selected month was %d" % elec_use_sum)
            print ("The sum of the electric cost for the selected month was %f" % elec_cost_sum)
            print ("The sum of the transmission costs for the selected month was %f" % trans_cost_sum)
            print ("The electrical cost totals for the month is %f" % tot_cost)
            print ("The cost per kwh is %f" % cost_per_unit)

            print ("\n")
            print ("***********************************************************")
            print ("\n")

            total_parkade = parkade_cost + park_trans_cost
            total_amenity = fc_elec_cost + fc_trans_cost
            total_henry = henry_singer_cost + henry_singer_trans_cost

            header = utility_type[:1].upper() + utility_type[1:]
            moname = monthname[:1].upper() + monthname[1:]
            theader = moname + " " + yearno + " " + header + " Bill Allocation"
            tgt_file = monthname + "-" + yearno + "-" + utility_type + ".pdf"
            second_tower_account = "rbt2.el001"
            first_tower_account = "rbt1.el001"
            first_amenity_center_account = "rbt1.68020"
            second_amenity_center_account = "rbt2.68020"
            first_parkade_account = "rbt1.el001"
            second_parkade_account = "rbt2.el001"
            gst_account = "gs001.001"

            if report_type == 'bill':
                gst_value = input("Please give the dollar amount (with no dollar signs) of the GST for the entire bill :")
                if gst_value is None:
                    print("I really need a GST dollar value to continue")
                    sys.exit(1)
                else:
                    print("Thank you!")
                    gst_true = Decimal(gst_value)
                    new_tot_cost = tot_cost + gst_true

                if multiples == 0:
                    pdf = FPDF()
                    pdf.add_page()
                    pdf.set_font("Times", 'B', 24) 
                    cell_width = (len(theader) * 4.3) + 20
                    pdf.cell(cell_width, 20, theader, ln=1, align="C")
                    pdf.set_font("Times", size=10) 
                    pdf.cell(cell_width, 10, curr_print, ln=1, align="C")
                    pdf.set_font("Times", 'U', 14) 
                    pdf.cell(70, 10, "Entity")
                    pdf.cell(40, 10, "Account Number")
                    pdf.cell(40, 10, "Usage Volume")
                    pdf.cell(40, 10, "Cost Incurred", ln=1)
                    pdf.set_font("Times", size=14) 
                    pdf.cell(70, 10, "Specific Retailer Costs")
                    pdf.cell(40, 10, first_tower_account)
                    pdf.cell(40, 10, '{:,.0f}'.format(henry_singer_usage), align="C")
                    pdf.cell(40, 10, '${:,.2f}'.format(total_henry), ln=1)
                    pdf.cell(70, 10, "Tower One Parkade Costs")
                    pdf.cell(40, 10, first_parkade_account)
                    pdf.cell(40, 10, '{:,.0f}'.format(park_et_elec_usage), align="C")
                    pdf.cell(40, 10, '${:,.2f}'.format(park_et_total_cost), ln=1)
                    pdf.cell(70, 10, "Tower Two Parkade Costs")
                    pdf.cell(40, 10, second_parkade_account)
                    pdf.cell(40, 10, '{:,.0f}'.format(park_wt_elec_usage), align="C")
                    pdf.cell(40, 10, '${:,.2f}'.format(park_wt_total_cost), ln=1)
                    pdf.cell(70, 10, "Tower One Fitness Ctr Costs")
                    pdf.cell(40, 10, first_amenity_center_account)
                    pdf.cell(40, 10, '{:,.0f}'.format(fc_et_usage), align="C")
                    pdf.cell(40, 10, '${:,.2f}'.format(fc_et_total_cost), ln=1)
                    pdf.cell(70, 10, "Tower Two Fitness Ctr Costs")
                    pdf.cell(40, 10, second_amenity_center_account)
                    pdf.cell(40, 10, '{:,.0f}'.format(fc_wt_usage), align="C")
                    pdf.cell(40, 10, '${:,.2f}'.format(fc_wt_total_cost), ln=1)
                    pdf.cell(70, 10, "Tower One Costs")
                    pdf.cell(40, 10, first_tower_account)
                    pdf.cell(40, 10, '{:,.0f}'.format(et_elec_usage_total), align="C")
                    pdf.cell(40, 10, '${:,.2f}'.format(et_grand_total), ln=1)
                    pdf.cell(70, 10, "Tower Two Costs", border="T")
                    pdf.cell(40, 10, second_tower_account, border="T")
                    pdf.cell(40, 10, '{:,.0f}'.format(wt_elec_usage_total), align="C", border="T")
                    pdf.cell(40, 10, '${:,.2f}'.format(wt_grand_total), border="T", ln=1)
                    pdf.cell(70, 10, "GST")
                    pdf.cell(80, 10, gst_account)
                    pdf.cell(40, 10, '${:,.2f}'.format(gst_true), ln=1)
                    pdf.cell(110, 10, "Totals", border="T")
                    pdf.cell(40, 10, '{:,.0f}'.format(elec_use_sum), border="T", align="C")
                    pdf.cell(40, 10, '${:,.2f}'.format(new_tot_cost), border="T")
                    pdf.output(tgt_file)

                elif multiples > 0:
                    pass

            elif report_type == 'variance':
                hsv = parkadev = et417 = et1829 = et3042 = et4350 = etcp = etfp1 = etfp2 = wt418 = wt1931 = wt3241 = wtcp = wtfp1 = wtfp2 = fcv = om = ''
                HDD = 'Not yet entered'
                CDD = 'Not yet entered'
                cur2 = conn.cursor()
                cur2.execute("""SELECT tracking_reading.meter_id, usage_amount FROM tracking_meter, tracking_reading WHERE tracking_meter.mstype = 'Monthly' AND tracking_meter.mtype = 'Climate' AND tracking_reading.meter_id=tracking_meter.id AND tracking_reading.month = '%s' AND tracking_reading.year = '%s'""" % (start_month, yearno))
                rows2 = cur2.fetchall()
                if rows2:
                    for row2 in rows2:
                        if row2[0] == 166:
                            HDD = row2[1]
                        elif row2[0] == 167:
                            CDD = row2[1]
                        else:
                            print ("Houston, we have a problem")

                cur12 = conn.cursor()
                cur12.execute("""SELECT tracking_reading.meter_id, usage_amount FROM tracking_meter, tracking_reading WHERE tracking_meter.mstype = 'Monthly' AND tracking_meter.mtype = 'Climate' AND tracking_reading.meter_id=tracking_meter.id AND tracking_reading.month = '%s' AND tracking_reading.year = '%s'""" % (start_month, lastyear))
                rows12 = cur12.fetchall()
                if rows12:
                    for row12 in rows12:
                        if row12[0] == 166:
                            HDDL = row12[1]
                        elif row12[0] == 167:
                            CDDL = row12[1]
                        else:
                            print ("Houston, we have a problem")



                ###Get occupancy data (if available)
                ETOL = 0.00
                WTOL = 0.00
                ETO = 0.000
                WTO = 0.000
                cur3 = conn.cursor()
                cur3.execute("""SELECT tracking_reading.meter_id, usage_amount FROM tracking_meter, tracking_reading WHERE tracking_meter.mstype = 'Monthly' AND tracking_meter.mtype = 'Occupancy' AND tracking_reading.meter_id=tracking_meter.id AND tracking_reading.month = '%s' AND tracking_reading.year = '%s'""" % (start_month, yearno))
                rows3 = cur3.fetchall()
                if rows3:
                    for row3 in rows3:
                        if row3[0] == 170:
                            ETO = row3[1]
                        elif row3[0] == 171:
                            WTO = row3[1]
                        else:
                            print ("Houston, we have a problem")

                cur13 = conn.cursor()
                cur13.execute("""SELECT tracking_reading.meter_id, usage_amount FROM tracking_meter, tracking_reading WHERE tracking_meter.mstype = 'Monthly' AND tracking_meter.mtype = 'Occupancy' AND tracking_reading.meter_id=tracking_meter.id AND tracking_reading.month = '%s' AND tracking_reading.year = '%s'""" % (start_month, lastyear))
                rows13 = cur13.fetchall()
                if rows13:
                    for row13 in rows13:
                        if row13[0] == 170:
                            ETOL = row13[1]
                        elif row13[0] == 171:
                            WTOL = row13[1]
                        else:
                            print ("Houston, we have a problem")





                ###Get the contracted amount for the present month
                contr_amt = list(filter(lambda b: b[0] == s_month_name[0][1], CONTRACT_AMOUNTS))
                contr_value = contr_amt[0][1]
                ###Get the summed amount of all meters on the original contract agreement
                contracted_use = sum(total_for_contract)

                ###Get any / all variance explanations that have been entered and print them.
                ###First, set all variance explanation variables to a generic phrase
                et417 = et1829 = et3042 = et4350 = etcp = parkadev = etfp1 = wt418 = wt1931 = wt3241 = wtcp = wtfp1 = wtfp2 = om = fcv = hsv = etfp2 = "No variance explanation given"
                cur4 = conn.cursor()
                cur4.execute("""SELECT id, detail, meter_affected_id FROM eap_tracker_energyvariance WHERE monthly_utility_explanation = 't' AND month = '%s' AND year = '%s'""" % (start_month, yearno))
                rows4 = cur4.fetchall()
                if rows4:
                    for row4 in rows4:
                        if row4[2] == 2:
                            et417 = row4[1]
                        elif row4[2] == 3:
                            et1829 = row4[1]
                        elif row4[2] == 4:
                            et3042 = row4[1]
                        elif row4[2] == 5:
                            et4350 = row4[1]
                        elif row4[2] == 6:
                            etcp = row4[1]
                        elif row4[2] == 7:
                            parkadev = row4[1]
                        elif row4[2] == 8:
                            etfp1 = row4[1]
                        elif row4[2] == 9:
                            wt418 = row4[1]
                        elif row4[2] == 10:
                            wt1931 = row4[1]
                        elif row4[2] == 11:
                            wt3241 = row4[1]
                        elif row4[2] == 12:
                            wtcp = row4[1]
                        elif row4[2] == 13:
                            wtfp1 = row4[1]
                        elif row4[2] == 14:
                            wtfp2 = row4[1]
                        elif row4[2] == 15:
                            om = row4[1]
                        elif row4[2] == 138:
                            fcv = row4[1]
                        elif row4[2] == 139:
                            hsv = row4[1]
                        elif row4[2] == 140:
                            etfp2 = row4[1]
                        else:
                            print ("Houston, this is too many problems")




                ###Get all of last year's usage data for the same month (for comparison purposes)
                l_electric_cost = []
                l_et_elec_cost = []
                l_wt_elec_cost = []
                l_electric_usage = []
                l_et_elec_usage = []
                l_wt_elec_usage = []
                l_trans_cost = []
                l_et_trans_cost = []
                l_wt_trans_cost = []
                l_total_sum = []
                ###These were added to make allowance for some missing data at the start of 2018
                l_henry_singer_usage = 0
                l_FP_8_1_ET = 0
                l_fc_elec_usage = 0
                cur1 = conn.cursor()
                cur1.execute("""SELECT tracking_reading.meter_id, usage_amount, usage_cost, transmission_cost FROM tracking_meter, tracking_reading WHERE tracking_meter.mstype = 'Monthly' AND tracking_meter.mtype = 'Electric' AND tracking_reading.meter_id=tracking_meter.id AND tracking_reading.month = '%s' AND tracking_reading.year = '%s'""" % (start_month, lastyear))  #AND recorded >= '%s' AND recorded <= '%s' """  % (start_date, end_date))
                rows1 = cur1.fetchall()
                if rows1:
                    for row1 in rows1:
                        if row1[0] == 2:
                            l_4_17_ET = row1[1]
                            l_electric_usage.append(row1[1])
                            l_et_elec_usage.append(row1[1])
                            l_electric_cost.append(row1[2])
                            l_et_elec_cost.append(row1[2])
                            l_trans_cost.append(row1[3])
                            l_et_trans_cost.append(row1[3])
                            l_total_sum.append(row1)
                        elif row1[0] == 3:
                            l_18_29_ET = row1[1]
                            l_electric_usage.append(row1[1])
                            l_et_elec_usage.append(row1[1])
                            l_electric_cost.append(row1[2])
                            l_et_elec_cost.append(row1[2])
                            l_trans_cost.append(row1[3])
                            l_et_trans_cost.append(row1[3])
                            l_total_sum.append(row1)
                        elif row1[0] == 4:
                            l_30_42_ET = row1[1]
                            l_electric_usage.append(row1[1])
                            l_et_elec_usage.append(row1[1])
                            l_electric_cost.append(row1[2])
                            l_et_elec_cost.append(row1[2])
                            l_trans_cost.append(row1[3])
                            l_et_trans_cost.append(row1[3])
                            l_total_sum.append(row1)
                        elif row1[0] == 5:
                            l_43_50_ET = row1[1]
                            l_electric_usage.append(row1[1])
                            l_et_elec_usage.append(row1[1])
                            l_electric_cost.append(row1[2])
                            l_et_elec_cost.append(row1[2])
                            l_trans_cost.append(row1[3])
                            l_et_trans_cost.append(row1[3])
                            l_total_sum.append(row1)
                        elif row1[0] == 6:
                            l_central_plant_ET = row1[1]
                            l_electric_usage.append(row1[1])
                            l_et_elec_usage.append(row1[1])
                            l_electric_cost.append(row1[2])
                            l_et_elec_cost.append(row1[2])
                            l_trans_cost.append(row1[3])
                            l_et_trans_cost.append(row1[3])
                            l_total_sum.append(row1)
                        elif row1[0] == 7:
                            l_parkade_use = row1[1]
                            l_electric_usage.append(row1[1])
                            ##Get parkade overall usage, then split to first and second portions
                            l_park_et_elec_usage = Decimal(l_parkade_use) * Decimal(0.565)
                            l_park_wt_elec_usage = l_parkade_use - l_park_et_elec_usage
                            ##Get parkade overall cost, then split to first and second portions
                            l_parkade_cost = row1[2]
                            l_electric_cost.append(row1[2])
                            l_park_et_elec_cost = Decimal(l_parkade_cost) * Decimal(0.565)
                            l_park_wt_elec_cost = parkade_cost - Decimal(l_park_et_elec_cost)
                            ##Get parkade overall transmission cost, then split to first and second portions
                            l_park_trans_cost = row1[3]
                            l_park_et_trans_cost = Decimal(l_park_trans_cost) * Decimal(0.565)
                            l_park_wt_trans_cost = l_park_trans_cost - Decimal(l_park_et_trans_cost)
                            l_park_et_total_cost = l_park_et_elec_cost + l_park_et_trans_cost
                            l_park_wt_total_cost = l_park_wt_elec_cost + l_park_wt_trans_cost
                            l_trans_cost.append(row1[3])
                            l_total_sum.append(row1)
                        elif row1[0] == 8:
                            l_FP_3_1_ET = row1[1]
                            l_electric_usage.append(row1[1])
                            l_et_elec_usage.append(row1[1])
                            l_electric_cost.append(row1[2])
                            l_et_elec_cost.append(row1[2])
                            l_trans_cost.append(row1[3])
                            l_et_trans_cost.append(row1[3])
                            l_total_sum.append(row1)
                        elif row1[0] == 9:
                            l_4_18_WT = row1[1]
                            l_electric_usage.append(row1[1])
                            l_wt_elec_usage.append(row1[1])
                            l_electric_cost.append(row1[2])
                            l_wt_elec_cost.append(row1[2])
                            l_trans_cost.append(row1[3])
                            l_wt_trans_cost.append(row1[3])
                            l_total_sum.append(row1)
                        elif row1[0] == 10:
                            l_19_31_WT = row1[1]
                            l_electric_usage.append(row1[1])
                            l_wt_elec_usage.append(row1[1])
                            l_electric_cost.append(row1[2])
                            l_wt_elec_cost.append(row1[2])
                            l_trans_cost.append(row1[3])
                            l_wt_trans_cost.append(row1[3])
                            l_total_sum.append(row1)
                        elif row1[0] == 11:
                            l_32_41_WT = row1[1]
                            l_electric_usage.append(row1[1])
                            l_wt_elec_usage.append(row1[1])
                            l_electric_cost.append(row1[2])
                            l_wt_elec_cost.append(row1[2])
                            l_trans_cost.append(row1[3])
                            l_wt_trans_cost.append(row1[3])
                            l_total_sum.append(row1)
                        elif row1[0] == 12:
                            l_central_plant_WT = row1[1]
                            l_electric_usage.append(row1[1])
                            l_wt_elec_usage.append(row1[1])
                            l_electric_cost.append(row1[2])
                            l_wt_elec_cost.append(row1[2])
                            l_trans_cost.append(row1[3])
                            l_wt_trans_cost.append(row1[3])
                            l_total_sum.append(row1)
                        elif row1[0] == 13:
                            l_FP_3_1_WT = row1[1]
                            l_electric_usage.append(row1[1])
                            l_wt_elec_usage.append(row1[1])
                            l_electric_cost.append(row1[2])
                            l_wt_elec_cost.append(row1[2])
                            l_trans_cost.append(row1[3])
                            l_wt_trans_cost.append(row1[3])
                            l_total_sum.append(row1)
                        elif row1[0] == 14:
                            l_FP_3_2_WT = row1[1]
                            l_electric_usage.append(row1[1])
                            l_wt_elec_usage.append(row1[1])
                            l_electric_cost.append(row1[2])
                            l_wt_elec_cost.append(row1[2])
                            l_trans_cost.append(row1[3])
                            l_wt_trans_cost.append(row1[3])
                            l_total_sum.append(row1)
                        elif row1[0] == 15:
                            l_205_555_8th = row1[1]
                            l_electric_usage.append(row1[1])
                            l_et_elec_usage.append(row1[1])
                            l_electric_cost.append(row1[2])
                            l_et_elec_cost.append(row1[2])
                            l_trans_cost.append(row1[3])
                            l_et_trans_cost.append(row1[3])
                            l_total_sum.append(row1)
                        elif row1[0] == 138:
                            l_electric_usage.append(row1[1])
                            l_fc_elec_usage = row1[1]
                            l_fc_et_usage = Decimal(l_fc_elec_usage) * Decimal(0.565)
                            l_fc_wt_usage = l_fc_elec_usage - l_fc_et_usage
                            l_electric_cost.append(row1[2])
                            l_fc_elec_cost = row1[2]
                            l_fc_et_cost = Decimal(l_fc_elec_cost) * Decimal(0.565)
                            l_fc_wt_cost = Decimal(l_fc_elec_cost) - Decimal(l_fc_et_cost)
                            l_trans_cost.append(row1[3])
                            l_fc_trans_cost = row1[3]
                            l_fc_et_trans_cost = Decimal(l_fc_trans_cost) * Decimal(0.565)
                            l_fc_wt_trans_cost = Decimal(l_fc_trans_cost) - Decimal(l_fc_et_trans_cost)
                            l_fc_et_total_cost = l_fc_et_cost + l_fc_et_trans_cost
                            l_fc_wt_total_cost = l_fc_wt_cost + l_fc_wt_trans_cost
                            l_total_sum.append(row1)
                        elif row1[0] == 139:
                            l_electric_usage.append(row1[1])
                            l_henry_singer_usage = row1[1] 
                            l_electric_cost.append(row1[2])
                            l_henry_singer_cost = row1[2]
                            l_trans_cost.append(row1[3])
                            l_henry_singer_trans_cost = row1[3]
                            l_henry_singer_total_cost = l_henry_singer_trans_cost + l_henry_singer_cost
                            l_total_sum.append(row1)
                        elif row1[0] == 140:
                            l_FP_8_1_ET = row1[1]
                            l_electric_usage.append(row1[1])
                            l_et_elec_usage.append(row1[1])
                            l_electric_cost.append(row1[2])
                            l_et_elec_cost.append(row1[2])
                            l_trans_cost.append(row1[3])
                            l_et_trans_cost.append(row1[3])
                            l_total_sum.append(row1)
                        else:
                            pass

                ##################Was commented out below here
                ##To address the end of year scenarios, with incrementing the year and changing the month to january
                if start_month == 1:
                    newyrstring = int(yearno) - 1
                else:
                    newyrstring = yearno
                ########################Was commented out above here
                pm_electric_cost = []
                pm_et_elec_cost = []
                pm_wt_elec_cost = []
                pm_electric_usage = []
                pm_et_elec_usage = []
                pm_wt_elec_usage = []
                pm_trans_cost = []
                pm_et_trans_cost = []
                pm_wt_trans_cost = []
                pm_total_sum = []
                cur2 = conn.cursor()
                cur2.execute("""SELECT tracking_reading.meter_id, usage_amount, usage_cost, transmission_cost FROM tracking_reading, tracking_meter WHERE tracking_reading.meter_id=tracking_meter.id AND tracking_reading.month = '%s' AND tracking_reading.year = '%s'""" % (prev_month, newyrstring))  #AND recorded >= '%s' AND recorded <= '%s' """  % (start_date, end_date))
                rows2 = cur2.fetchall()
                if rows2:
                    for row2 in rows2:
                        if row2[0] == 2:
                            pm_4_17_ET = row2[1]
                            pm_electric_usage.append(row2[1])
                            pm_et_elec_usage.append(row2[1])
                            pm_electric_cost.append(row2[2])
                            pm_et_elec_cost.append(row2[2])
                            pm_trans_cost.append(row2[3])
                            pm_et_trans_cost.append(row2[3])
                            pm_total_sum.append(row2)
                        elif row2[0] == 3:
                            pm_18_29_ET = row2[1]
                            pm_electric_usage.append(row2[1])
                            pm_et_elec_usage.append(row2[1])
                            pm_electric_cost.append(row2[2])
                            pm_et_elec_cost.append(row2[2])
                            pm_trans_cost.append(row2[3])
                            pm_et_trans_cost.append(row2[3])
                            pm_total_sum.append(row2)
                        elif row2[0] == 4:
                            pm_30_42_ET = row2[1]
                            pm_electric_usage.append(row2[1])
                            pm_et_elec_usage.append(row2[1])
                            pm_electric_cost.append(row2[2])
                            pm_et_elec_cost.append(row2[2])
                            pm_trans_cost.append(row2[3])
                            pm_et_trans_cost.append(row2[3])
                            pm_total_sum.append(row2)
                        elif row2[0] == 5:
                            pm_43_50_ET = row2[1]
                            pm_electric_usage.append(row2[1])
                            pm_et_elec_usage.append(row2[1])
                            pm_electric_cost.append(row2[2])
                            pm_et_elec_cost.append(row2[2])
                            pm_trans_cost.append(row2[3])
                            pm_et_trans_cost.append(row2[3])
                            pm_total_sum.append(row2)
                        elif row2[0] == 6:
                            pm_central_plant_ET = row2[1]
                            pm_electric_usage.append(row2[1])
                            pm_et_elec_usage.append(row2[1])
                            pm_electric_cost.append(row2[2])
                            pm_et_elec_cost.append(row2[2])
                            pm_trans_cost.append(row2[3])
                            pm_et_trans_cost.append(row2[3])
                            pm_total_sum.append(row2)
                        elif row2[0] == 7:
                            pm_parkade_use = row2[1]
                            pm_electric_usage.append(row2[1])
                            ##Get parkade overall usage, then split to first and second portions
                            pm_park_et_elec_usage = Decimal(pm_parkade_use) * Decimal(0.565)
                            pm_park_wt_elec_usage = pm_parkade_use - pm_park_et_elec_usage
                            ##Get parkade overall cost, then split to first and second portions
                            pm_parkade_cost = row2[2]
                            pm_electric_cost.append(row2[2])
                            pm_park_et_elec_cost = Decimal(pm_parkade_cost) * Decimal(0.565)
                            pm_park_wt_elec_cost = parkade_cost - Decimal(pm_park_et_elec_cost)
                            ##Get parkade overall transmission cost, then split to first and second portions
                            pm_park_trans_cost = row2[3]
                            pm_park_et_trans_cost = Decimal(pm_park_trans_cost) * Decimal(0.565)
                            pm_park_wt_trans_cost = pm_park_trans_cost - Decimal(pm_park_et_trans_cost)
                            pm_park_et_total_cost = pm_park_et_elec_cost + pm_park_et_trans_cost
                            pm_park_wt_total_cost = pm_park_wt_elec_cost + pm_park_wt_trans_cost
                            pm_trans_cost.append(row2[3])
                            pm_total_sum.append(row2)
                        elif row2[0] == 8:
                            pm_FP_3_1_ET = row2[1]
                            pm_electric_usage.append(row2[1])
                            pm_et_elec_usage.append(row2[1])
                            pm_electric_cost.append(row2[2])
                            pm_et_elec_cost.append(row2[2])
                            pm_trans_cost.append(row2[3])
                            pm_et_trans_cost.append(row2[3])
                            pm_total_sum.append(row2)
                        elif row2[0] == 9:
                            pm_4_18_WT = row2[1]
                            pm_electric_usage.append(row2[1])
                            pm_wt_elec_usage.append(row2[1])
                            pm_electric_cost.append(row2[2])
                            pm_wt_elec_cost.append(row2[2])
                            pm_trans_cost.append(row2[3])
                            pm_wt_trans_cost.append(row2[3])
                            pm_total_sum.append(row2)
                        elif row2[0] == 10:
                            pm_19_31_WT = row2[1]
                            pm_electric_usage.append(row2[1])
                            pm_wt_elec_usage.append(row2[1])
                            pm_electric_cost.append(row2[2])
                            pm_wt_elec_cost.append(row2[2])
                            pm_trans_cost.append(row2[3])
                            pm_wt_trans_cost.append(row2[3])
                            pm_total_sum.append(row2)
                        elif row2[0] == 11:
                            pm_32_41_WT = row2[1]
                            pm_electric_usage.append(row2[1])
                            pm_wt_elec_usage.append(row2[1])
                            pm_electric_cost.append(row2[2])
                            pm_wt_elec_cost.append(row2[2])
                            pm_trans_cost.append(row2[3])
                            pm_wt_trans_cost.append(row2[3])
                            pm_total_sum.append(row2)
                        elif row2[0] == 12:
                            pm_central_plant_WT = row2[1]
                            pm_electric_usage.append(row2[1])
                            pm_wt_elec_usage.append(row2[1])
                            pm_electric_cost.append(row2[2])
                            pm_wt_elec_cost.append(row2[2])
                            pm_trans_cost.append(row2[3])
                            pm_wt_trans_cost.append(row2[3])
                            pm_total_sum.append(row2)
                        elif row2[0] == 13:
                            pm_FP_3_1_WT = row2[1]
                            pm_electric_usage.append(row2[1])
                            pm_wt_elec_usage.append(row2[1])
                            pm_electric_cost.append(row2[2])
                            pm_wt_elec_cost.append(row2[2])
                            pm_trans_cost.append(row2[3])
                            pm_wt_trans_cost.append(row2[3])
                            pm_total_sum.append(row2)
                        elif row2[0] == 14:
                            pm_FP_3_2_WT = row2[1]
                            pm_electric_usage.append(row2[1])
                            pm_wt_elec_usage.append(row2[1])
                            pm_electric_cost.append(row2[2])
                            pm_wt_elec_cost.append(row2[2])
                            pm_trans_cost.append(row2[3])
                            pm_wt_trans_cost.append(row2[3])
                            pm_total_sum.append(row2)
                        elif row2[0] == 15:
                            pm_205_555_8th = row2[1]
                            pm_electric_usage.append(row2[1])
                            pm_et_elec_usage.append(row2[1])
                            pm_electric_cost.append(row2[2])
                            pm_et_elec_cost.append(row2[2])
                            pm_trans_cost.append(row2[3])
                            pm_et_trans_cost.append(row2[3])
                            pm_total_sum.append(row2)
                        elif row2[0] == 138:
                            pm_electric_usage.append(row2[1])
                            pm_fc_elec_usage = row2[1]
                            pm_fc_et_usage = Decimal(pm_fc_elec_usage) * Decimal(0.565)
                            pm_fc_wt_usage = pm_fc_elec_usage - pm_fc_et_usage
                            pm_electric_cost.append(row2[2])
                            pm_fc_elec_cost = row2[2]
                            pm_fc_et_cost = Decimal(pm_fc_elec_cost) * Decimal(0.565)
                            pm_fc_wt_cost = Decimal(pm_fc_elec_cost) - Decimal(pm_fc_et_cost)
                            pm_trans_cost.append(row2[3])
                            pm_fc_trans_cost = row2[3]
                            pm_fc_et_trans_cost = Decimal(pm_fc_trans_cost) * Decimal(0.565)
                            pm_fc_wt_trans_cost = Decimal(pm_fc_trans_cost) - Decimal(pm_fc_et_trans_cost)
                            pm_fc_et_total_cost = pm_fc_et_cost + pm_fc_et_trans_cost
                            pm_fc_wt_total_cost = pm_fc_wt_cost + pm_fc_wt_trans_cost
                            pm_total_sum.append(row2)
                        elif row2[0] == 139:
                            pm_electric_usage.append(row2[1])
                            pm_henry_singer_usage = row2[1]
                            pm_electric_cost.append(row2[2])
                            pm_henry_singer_cost = row2[2]
                            pm_trans_cost.append(row2[3])
                            pm_henry_singer_trans_cost = row2[3]
                            pm_henry_singer_total_cost = pm_henry_singer_trans_cost + pm_henry_singer_cost
                            pm_total_sum.append(row2)
                        elif row2[0] == 140:
                            pm_FP_8_1_ET = row2[1]
                            pm_electric_usage.append(row2[1])
                            pm_et_elec_usage.append(row2[1])
                            pm_electric_cost.append(row2[2])
                            pm_et_elec_cost.append(row2[2])
                            pm_trans_cost.append(row2[3])
                            pm_et_trans_cost.append(row2[3])
                            pm_total_sum.append(row2)
                        else:
                            pass


                    print ("%s %s" % (s_month_name[0][1], lastyear))
                    l_et_elec_usage_total = sum(l_et_elec_usage)
                    print ("The first tower usage total is %d" % l_et_elec_usage_total)
                    l_et_use_per_foot = float(l_et_elec_usage_total) / float(ET_FOOTAGE)
                    print ("The usage per square foot is %f" % l_et_use_per_foot)
                    l_et_elec_cost_total = sum(l_et_elec_cost)
                    print ("The first tower cost total is %f" % l_et_elec_cost_total)
                    l_et_elec_trans_total = sum(l_et_trans_cost)
                    print ("The first tower transmission cost total is %f" % l_et_elec_trans_total)
                    l_et_grand_total = l_et_elec_cost_total + l_et_elec_trans_total
                    print ("The grand total first tower cost is %f" % l_et_grand_total)
                    l_et_cost_per_foot = float(l_et_grand_total) / float(ET_FOOTAGE)
                    print ("The cost per square foot is %f" % l_et_cost_per_foot)
                    print ("*******************************************************")
                    l_wt_elec_usage_total = sum(l_wt_elec_usage)
                    print ("The second tower usage total is %d" % l_wt_elec_usage_total)
                    l_wt_use_per_foot = float(l_wt_elec_usage_total) / float(WT_FOOTAGE)
                    print ("The usage per square foot is %f" % l_wt_use_per_foot)
                    l_wt_elec_cost_total = sum(l_wt_elec_cost)
                    print ("The second tower cost total is %f" % l_wt_elec_cost_total)
                    l_wt_elec_trans_total = sum(l_wt_trans_cost)
                    print ("The second tower transmission cost total is %f" % l_wt_elec_trans_total)
                    l_wt_grand_total = l_wt_elec_cost_total + l_wt_elec_trans_total
                    print ("The grand total second tower cost is %f" % l_wt_grand_total)
                    l_wt_cost_per_foot = float(l_wt_grand_total) / float(WT_FOOTAGE)
                    print ("The cost per square foot is %f" % l_wt_cost_per_foot)
                    print ("********************************************************")
                    print ("The parkade usage is %d" % l_parkade_use)
                    print ("********************************************************")
                    l_elec_use_sum = sum(l_electric_usage)
                    l_elec_cost_sum = sum(l_electric_cost)
                    l_trans_cost_sum = sum(l_trans_cost)
                    l_tot_cost = l_elec_cost_sum + l_trans_cost_sum
                    l_cost_per_unit = l_tot_cost / l_elec_use_sum
                    print ("The sum of the electric usage for the selected month was %d" % l_elec_use_sum)
                    print ("The sum of the electric cost for the selected month was %f" % l_elec_cost_sum)
                    print ("The sum of the transmission costs for the selected month was %f" % l_trans_cost_sum)
                    print ("The electrical cost totals for the month is %f" % l_tot_cost)
                    print ("The cost per kwh is %f" % l_cost_per_unit)
                    print ("********************************************************")
                    print ("\n")

                    l_total_parkade = l_parkade_cost + l_park_trans_cost
                    try:
                        l_total_amenity = l_fc_elec_cost + l_fc_trans_cost
                    except NameError: 
                        l_total_amenity = 0
                    try: 
                        l_henry_singer_cost
                    except NameError:
                        l_henry_singer_cost = 0


                    print ("%s %s" % ("Previous Month", newyrstring))  ##This will be wrong until I update it
                    pm_et_elec_usage_total = sum(pm_et_elec_usage)
                    print ("The first tower usage total is %d" % pm_et_elec_usage_total)
                    pm_et_use_per_foot = float(pm_et_elec_usage_total) / float(ET_FOOTAGE)
                    print ("The usage per square foot is %f" % pm_et_use_per_foot)
                    pm_et_elec_cost_total = sum(pm_et_elec_cost)
                    print ("The first tower cost total is %f" % pm_et_elec_cost_total)
                    pm_et_elec_trans_total = sum(pm_et_trans_cost)
                    print ("The first tower transmission cost total is %f" % pm_et_elec_trans_total)
                    pm_et_grand_total = pm_et_elec_cost_total + pm_et_elec_trans_total
                    print ("The grand total first tower cost is %f" % pm_et_grand_total)
                    pm_et_cost_per_foot = float(pm_et_grand_total) / float(ET_FOOTAGE)
                    print ("The cost per square foot is %f" % pm_et_cost_per_foot)
                    print ("*******************************************************")
                    pm_wt_elec_usage_total = sum(pm_wt_elec_usage)
                    print ("The second tower usage total is %d" % pm_wt_elec_usage_total)
                    pm_wt_use_per_foot = float(pm_wt_elec_usage_total) / float(WT_FOOTAGE)
                    print ("The usage per square foot is %f" % pm_wt_use_per_foot)
                    pm_wt_elec_cost_total = sum(pm_wt_elec_cost)
                    print ("The second tower cost total is %f" % pm_wt_elec_cost_total)
                    pm_wt_elec_trans_total = sum(pm_wt_trans_cost)
                    print ("The second tower transmission cost total is %f" % pm_wt_elec_trans_total)
                    pm_wt_grand_total = pm_wt_elec_cost_total + pm_wt_elec_trans_total
                    print ("The grand total second tower cost is %f" % pm_wt_grand_total)
                    pm_wt_cost_per_foot = float(pm_wt_grand_total) / float(WT_FOOTAGE)
                    print ("The cost per square foot is %f" % pm_wt_cost_per_foot)
                    print ("********************************************************")
                    print ("The parkade usage is %d" % pm_parkade_use)
                    print ("********************************************************")
                    pm_elec_use_sum = sum(pm_electric_usage)
                    pm_elec_cost_sum = sum(pm_electric_cost)
                    pm_trans_cost_sum = sum(pm_trans_cost)
                    pm_tot_cost = pm_elec_cost_sum + pm_trans_cost_sum
                    pm_cost_per_unit = pm_tot_cost / pm_elec_use_sum
                    print ("The sum of the electric usage for the selected month was %d" % pm_elec_use_sum)
                    print ("The sum of the electric cost for the selected month was %f" % pm_elec_cost_sum)
                    print ("The sum of the transmission costs for the selected month was %f" % pm_trans_cost_sum)
                    print ("The electrical cost totals for the month is %f" % pm_tot_cost)
                    print ("The cost per kwh is %f" % pm_cost_per_unit)

                    pm_total_parkade = pm_parkade_cost + pm_park_trans_cost
                    pm_total_amenity = pm_fc_elec_cost + pm_fc_trans_cost
                    pm_total_henry = pm_henry_singer_cost + pm_henry_singer_trans_cost
                    
                    print ("\n")
                    print (et417)
                    print ("\n")
                    theader = moname + " " + yearno + " " + header + " Usage Variances"

                    tgt_file = monthname + "-" + yearno + "-" + utility_type + "variance_report.pdf"
                    pdf = FPDF()
                    pdf.add_page()
                    pdf.set_font("Times", 'B', 24) 
                    cell_width = (len(theader) * 4.3) + 20
                    pdf.cell(cell_width, 40, theader, ln=1)
                    pdf.cell(120, 10, "Year Over Year Comparison", ln=1)
                    pdf.set_font("Times", 'U', 14) 
                    pdf.cell(70, 10, "Meter Coverage")
                    pdf.cell(40, 10, "Current Usage")
                    pdf.cell(40, 10, "Last Year")
                    pdf.cell(40, 10, "Percent Increase", ln=1)
                    pdf.set_font("Times", size=14) 
                    pdf.cell(70, 10, "Specific Retailer")
                    pdf.cell(40, 10, '{:,.0f}'.format(henry_singer_usage), align="C")
                    pdf.cell(40, 10, '{:,.0f}'.format(l_henry_singer_usage), align="C")
                    if l_henry_singer_usage > 0:
                        hs_pct_increase = ((float(henry_singer_usage)-float(l_henry_singer_usage))/float(l_henry_singer_usage))*100
                    else:
                        hs_pct_increase = 0
                    pdf.cell(40, 10, '{:,.2f}%'.format(hs_pct_increase), ln=1)
                    pdf.set_fill_color(240,240,240)
                    pdf.cell(70, 10, "Parkade", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(parkade_use), align="C", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(l_parkade_use), align="C", fill=True)
                    parkade_pct_increase = ((float(parkade_use)-float(l_parkade_use))/float(l_parkade_use))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(parkade_pct_increase), fill=True, ln=1)
                    pdf.cell(70, 10, "Tower One 4-17")
                    pdf.cell(40, 10, '{:,.0f}'.format(c_4_17_ET), align="C")
                    pdf.cell(40, 10, '{:,.0f}'.format(l_4_17_ET), align="C")
                    et_4_17_pct_increase = ((float(c_4_17_ET)-float(l_4_17_ET))/float(l_4_17_ET))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(et_4_17_pct_increase), ln=1)
                    pdf.set_fill_color(240,240,240)
                    pdf.cell(70, 10, "Tower One 18-29", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(c_18_29_ET), align="C", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(l_18_29_ET), align="C", fill=True)
                    et_18_29_pct_increase = ((float(c_18_29_ET)-float(l_18_29_ET))/float(l_18_29_ET))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(et_18_29_pct_increase), fill=True, ln=1)
                    pdf.cell(70, 10, "Tower One 30-42")
                    pdf.cell(40, 10, '{:,.0f}'.format(c_30_42_ET), align="C")
                    pdf.cell(40, 10, '{:,.0f}'.format(l_30_42_ET), align="C")
                    et_30_42_pct_increase = ((float(c_30_42_ET)-float(l_30_42_ET))/float(l_30_42_ET))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(et_30_42_pct_increase), ln=1)
                    pdf.set_fill_color(240,240,240)
                    pdf.cell(70, 10, "Tower One 43-50", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(c_43_50_ET), align="C", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(l_43_50_ET), align="C", fill=True)
                    et_43_50_pct_increase = ((float(c_43_50_ET)-float(l_43_50_ET))/float(l_43_50_ET))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(et_43_50_pct_increase), fill=True, ln=1)
                    pdf.cell(70, 10, "Tower One Central Plant")
                    pdf.cell(40, 10, '{:,.0f}'.format(central_plant_ET), align="C")
                    pdf.cell(40, 10, '{:,.0f}'.format(l_central_plant_ET), align="C")
                    et_cp_pct_increase = ((float(central_plant_ET)-float(l_central_plant_ET))/float(l_central_plant_ET))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(et_cp_pct_increase), ln=1)
                    pdf.set_fill_color(240,240,240)
                    pdf.cell(70, 10, "Tower One Low Rise Fire Pump", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(FP_3_1_ET), align="C", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(l_FP_3_1_ET), align="C", fill=True)
                    et_fp_31_pct_increase = ((float(FP_3_1_ET)-float(l_FP_3_1_ET))/float(l_FP_3_1_ET))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(et_fp_31_pct_increase), fill=True, ln=1)
                    pdf.cell(70, 10, "Tower One High Rise Fire Pump")
                    pdf.cell(40, 10, '{:,.0f}'.format(FP_8_1_ET), align="C")
                    pdf.cell(40, 10, '{:,.0f}'.format(l_FP_8_1_ET), align="C")
                    if l_FP_8_1_ET > 0:
                        et_fp_81_pct_increase = ((float(FP_8_1_ET)-float(l_FP_8_1_ET))/float(l_FP_8_1_ET))*100
                    else:
                        et_fp_81_pct_increase = 0
                    pdf.cell(40, 10, '{:,.2f}%'.format(et_fp_81_pct_increase), ln=1)
                    pdf.set_fill_color(240,240,240)
                    pdf.cell(70, 10, "Tower Two 4-18", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(c_4_18_WT), align="C", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(l_4_18_WT), align="C", fill=True)
                    wt_4_18_pct_increase = ((float(c_4_18_WT)-float(l_4_18_WT))/float(l_4_18_WT))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(wt_4_18_pct_increase), fill=True, ln=1)
                    pdf.cell(70, 10, "Tower Two 19-31")
                    pdf.cell(40, 10, '{:,.0f}'.format(c_19_31_WT), align="C")
                    pdf.cell(40, 10, '{:,.0f}'.format(l_19_31_WT), align="C")
                    wt_19_31_pct_increase = ((float(c_19_31_WT)-float(l_19_31_WT))/float(l_19_31_WT))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(wt_19_31_pct_increase), ln=1)
                    pdf.set_fill_color(240,240,240)
                    pdf.cell(70, 10, "Tower Two 32-41", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(c_32_41_WT), align="C", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(l_32_41_WT), align="C", fill=True)
                    wt_32_41_pct_increase = ((float(c_32_41_WT)-float(l_32_41_WT))/float(l_32_41_WT))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(wt_32_41_pct_increase), fill=True, ln=1)
                    pdf.cell(70, 10, "Tower Two Central Plant")
                    pdf.cell(40, 10, '{:,.0f}'.format(central_plant_WT), align="C")
                    pdf.cell(40, 10, '{:,.0f}'.format(l_central_plant_WT), align="C")
                    wt_cp_pct_increase = ((float(central_plant_WT)-float(l_central_plant_WT))/float(l_central_plant_WT))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(wt_cp_pct_increase), ln=1)
                    pdf.set_fill_color(240,240,240)
                    pdf.cell(70, 10, "Tower Two Low Rise Fire Pump", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(FP_3_1_WT), align="C", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(l_FP_3_1_WT), align="C", fill=True)
                    wt_fp_31_pct_increase = ((float(FP_3_1_WT)-float(l_FP_3_1_WT))/float(l_FP_3_1_WT))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(wt_fp_31_pct_increase), fill=True, ln=1)
                    pdf.cell(70, 10, "Tower Two High Rise Fire Pump")
                    pdf.cell(40, 10, '{:,.0f}'.format(FP_3_2_WT), align="C")
                    pdf.cell(40, 10, '{:,.0f}'.format(l_FP_3_2_WT), align="C")
                    wt_fp_32_pct_increase = ((float(FP_3_2_WT)-float(l_FP_3_2_WT))/float(l_FP_3_2_WT))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(wt_fp_32_pct_increase), ln=1)
                    pdf.set_fill_color(240,240,240)
                    pdf.cell(70, 10, "205-555 8th", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(c_205_555_8th), align="C", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(l_205_555_8th), align="C", fill=True)
                    d208_pct_increase = ((float(c_205_555_8th)-float(l_205_555_8th))/float(l_205_555_8th))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(d208_pct_increase), fill=True, ln=1)
                    pdf.cell(70, 10, "Amenity Space")
                    pdf.cell(40, 10, '{:,.0f}'.format(fc_elec_usage), align="C")
                    pdf.cell(40, 10, '{:,.0f}'.format(l_fc_elec_usage), align="C")
                    if l_fc_elec_usage > 0:
                        fc_pct_increase = ((float(fc_elec_usage)-float(l_fc_elec_usage))/float(l_fc_elec_usage))*100
                    else:
                        fc_pct_increase = 0
                    pdf.cell(40, 10, '{:,.2f}%'.format(fc_pct_increase), ln=1)
                    pdf.cell(70, 10, "Totals", border="T")
                    pdf.cell(40, 10, '{:,.0f}'.format(elec_use_sum), border="T", align="C")
                    pdf.cell(40, 10, '{:,.0f}'.format(l_elec_use_sum), border="T")
                    total_pct_increase = ((float(elec_use_sum)-float(l_elec_use_sum))/float(l_elec_use_sum))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(total_pct_increase), ln=1)


                    pdf.add_page()
                    pdf.set_font("Times", 'B', 24) 
                    celpm_width = (len(theader) * 4.3) + 20
                    pdf.cell(celpm_width, 40, theader, ln=1)
                    pdf.cell(120, 10, "Last Month Comparison", ln=1)
                    pdf.set_font("Times", 'U', 14) 
                    pdf.cell(70, 10, "Meter Coverage")
                    pdf.cell(40, 10, "Current Usage")
                    pdf.cell(40, 10, "Last Month")
                    pdf.cell(40, 10, "Percent Increase", ln=1)
                    pdf.set_font("Times", size=14) 
                    pdf.cell(70, 10, "Specific Retailer")
                    pdf.cell(40, 10, '{:,.0f}'.format(henry_singer_usage), align="C")
                    pdf.cell(40, 10, '{:,.0f}'.format(pm_henry_singer_usage), align="C")
                    hs_pct_increase = ((float(henry_singer_usage)-float(pm_henry_singer_usage))/float(pm_henry_singer_usage))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(hs_pct_increase), ln=1)
                    pdf.set_fill_color(204,204,179)
                    pdf.cell(70, 10, "Parkade", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(parkade_use), align="C", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(pm_parkade_use), align="C", fill=True)
                    parkade_pct_increase = ((float(parkade_use)-float(pm_parkade_use))/float(pm_parkade_use))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(parkade_pct_increase), fill=True, ln=1)
                    pdf.cell(70, 10, "Tower One 4-17")
                    pdf.cell(40, 10, '{:,.0f}'.format(c_4_17_ET), align="C")
                    pdf.cell(40, 10, '{:,.0f}'.format(pm_4_17_ET), align="C")
                    et_4_17_pct_increase = ((float(c_4_17_ET)-float(pm_4_17_ET))/float(pm_4_17_ET))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(et_4_17_pct_increase), ln=1)
                    pdf.set_fill_color(204,204,179)
                    pdf.cell(70, 10, "Tower One 18-29", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(c_18_29_ET), align="C", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(pm_18_29_ET), align="C", fill=True)
                    et_18_29_pct_increase = ((float(c_18_29_ET)-float(pm_18_29_ET))/float(pm_18_29_ET))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(et_18_29_pct_increase), fill=True, ln=1)
                    pdf.cell(70, 10, "Tower One 30-42")
                    pdf.cell(40, 10, '{:,.0f}'.format(c_30_42_ET), align="C")
                    pdf.cell(40, 10, '{:,.0f}'.format(pm_30_42_ET), align="C")
                    et_30_42_pct_increase = ((float(c_30_42_ET)-float(pm_30_42_ET))/float(pm_30_42_ET))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(et_30_42_pct_increase), ln=1)
                    pdf.set_fill_color(204,204,179)
                    pdf.cell(70, 10, "Tower One 43-50", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(c_43_50_ET), align="C", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(pm_43_50_ET), align="C", fill=True)
                    et_43_50_pct_increase = ((float(c_43_50_ET)-float(pm_43_50_ET))/float(pm_43_50_ET))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(et_43_50_pct_increase), fill=True, ln=1)
                    pdf.cell(70, 10, "Tower One Central Plant")
                    pdf.cell(40, 10, '{:,.0f}'.format(central_plant_ET), align="C")
                    pdf.cell(40, 10, '{:,.0f}'.format(pm_central_plant_ET), align="C")
                    et_cp_pct_increase = ((float(central_plant_ET)-float(pm_central_plant_ET))/float(pm_central_plant_ET))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(et_cp_pct_increase), ln=1)
                    pdf.set_fill_color(204,204,179)
                    pdf.cell(70, 10, "Tower One Low Rise Fire Pump", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(FP_3_1_ET), align="C", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(pm_FP_3_1_ET), align="C", fill=True)
                    et_fp_31_pct_increase = ((float(FP_3_1_ET)-float(pm_FP_3_1_ET))/float(pm_FP_3_1_ET))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(et_fp_31_pct_increase), fill=True, ln=1)
                    pdf.cell(70, 10, "Tower One High Rise Fire Pump")
                    pdf.cell(40, 10, '{:,.0f}'.format(FP_8_1_ET), align="C")
                    pdf.cell(40, 10, '{:,.0f}'.format(pm_FP_8_1_ET), align="C")
                    et_fp_81_pct_increase = ((float(FP_8_1_ET)-float(pm_FP_8_1_ET))/float(pm_FP_8_1_ET))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(et_fp_81_pct_increase), ln=1)
                    pdf.set_fill_color(204,204,179)
                    pdf.cell(70, 10, "Tower Two 4-18", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(c_4_18_WT), align="C", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(pm_4_18_WT), align="C", fill=True)
                    wt_4_18_pct_increase = ((float(c_4_18_WT)-float(pm_4_18_WT))/float(pm_4_18_WT))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(wt_4_18_pct_increase), fill=True, ln=1)
                    pdf.cell(70, 10, "Tower Two 19-31")
                    pdf.cell(40, 10, '{:,.0f}'.format(c_19_31_WT), align="C")
                    pdf.cell(40, 10, '{:,.0f}'.format(pm_19_31_WT), align="C")
                    wt_19_31_pct_increase = ((float(c_19_31_WT)-float(pm_19_31_WT))/float(pm_19_31_WT))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(wt_19_31_pct_increase), ln=1)
                    pdf.set_fill_color(204,204,179)
                    pdf.cell(70, 10, "Tower Two 32-41", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(c_32_41_WT), align="C", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(pm_32_41_WT), align="C", fill=True)
                    wt_32_41_pct_increase = ((float(c_32_41_WT)-float(pm_32_41_WT))/float(pm_32_41_WT))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(wt_32_41_pct_increase), fill=True, ln=1)
                    pdf.cell(70, 10, "Tower Two Central Plant")
                    pdf.cell(40, 10, '{:,.0f}'.format(central_plant_WT), align="C")
                    pdf.cell(40, 10, '{:,.0f}'.format(pm_central_plant_WT), align="C")
                    wt_cp_pct_increase = ((float(central_plant_WT)-float(pm_central_plant_WT))/float(pm_central_plant_WT))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(wt_cp_pct_increase), ln=1)
                    pdf.set_fill_color(204,204,179)
                    pdf.cell(70, 10, "Tower Two Low Rise Fire Pump", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(FP_3_1_WT), align="C", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(pm_FP_3_1_WT), align="C", fill=True)
                    wt_fp_31_pct_increase = ((float(FP_3_1_WT)-float(pm_FP_3_1_WT))/float(pm_FP_3_1_WT))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(wt_fp_31_pct_increase), fill=True, ln=1)
                    pdf.cell(70, 10, "Tower Two High Rise Fire Pump")
                    pdf.cell(40, 10, '{:,.0f}'.format(FP_3_2_WT), align="C")
                    pdf.cell(40, 10, '{:,.0f}'.format(pm_FP_3_2_WT), align="C")
                    wt_fp_32_pct_increase = ((float(FP_3_2_WT)-float(pm_FP_3_2_WT))/float(pm_FP_3_2_WT))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(wt_fp_32_pct_increase), ln=1)
                    pdf.set_fill_color(204,204,179)
                    pdf.cell(70, 10, "205-555 8th", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(c_205_555_8th), align="C", fill=True)
                    pdf.cell(40, 10, '{:,.0f}'.format(pm_205_555_8th), align="C", fill=True)
                    d208_pct_increase = ((float(c_205_555_8th)-float(pm_205_555_8th))/float(pm_205_555_8th))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(d208_pct_increase), fill=True, ln=1)
                    pdf.cell(70, 10, "Amenity Space")
                    pdf.cell(40, 10, '{:,.0f}'.format(fc_elec_usage), align="C")
                    pdf.cell(40, 10, '{:,.0f}'.format(pm_fc_elec_usage), align="C")
                    fc_pct_increase = ((float(fc_elec_usage)-float(pm_fc_elec_usage))/float(pm_fc_elec_usage))*100
                    pdf.cell(40, 10, '{:,.2f}%'.format(fc_pct_increase), ln=1)
                    pdf.cell(70, 10, "Totals", border="T")
                    pdf.cell(40, 10, '{:,.0f}'.format(elec_use_sum), border="T", align="C")
                    pdf.cell(40, 10, '{:,.0f}'.format(pm_elec_use_sum), border="T")
                    total_pct_increase = ((float(elec_use_sum)-float(pm_elec_use_sum))/float(pm_elec_use_sum))*100


                    pdf.add_page()
                    pdf.set_font("Times", 'B', 24) 
                    celpm_width = (len(theader) * 4.3) + 20
                    pdf.cell(celpm_width, 40, theader, ln=1)
                    pdf.set_font("Times", 'B', 16) 
                    pdf.cell(120, 10, "Variance Explanations", ln=1)
                    pdf.set_font("Times", 'U', 14) 
                    pdf.cell(90, 10, "Meter Coverage")
                    pdf.cell(100, 10, "Variance Explanation", ln=1)
                    pdf.set_font("Times", size=14) 
                    pdf.cell(90, 10, "Specific Retailer")
                    pdf.set_font("Times", size=10) 
                    pdf.cell(100, 10, hsv, ln=1)
                    pdf.set_font("Times", size=14) 
                    pdf.set_fill_color(240,240,240)
                    pdf.cell(90, 10, "Parkade", fill=True)
                    pdf.set_font("Times", size=10) 
                    pdf.cell(100, 10, parkadev, fill=True, ln=1)
                    pdf.set_font("Times", size=14) 
                    pdf.cell(90, 10, "Tower One 4-17")
                    pdf.set_font("Times", size=10) 
                    pdf.cell(100, 10, et417, ln=1)
                    pdf.set_font("Times", size=14) 
                    pdf.set_fill_color(218,230,241)
                    pdf.cell(90, 10, "Tower One 18-29", fill=True)
                    pdf.set_font("Times", size=10) 
                    pdf.cell(100, 10, et1829, fill=True, ln=1)
                    pdf.set_font("Times", size=14) 
                    pdf.cell(90, 10, "Tower One 30-42")
                    pdf.set_font("Times", size=10) 
                    pdf.cell(100, 10, et3042, ln=1)
                    pdf.set_font("Times", size=14) 
                    pdf.set_fill_color(218,230,241)
                    pdf.cell(90, 10, "Tower One 43-50", fill=True)
                    pdf.set_font("Times", size=10) 
                    pdf.cell(100, 10, et4350, fill=True, ln=1)
                    pdf.set_font("Times", size=14) 
                    pdf.cell(90, 10, "Tower One Central Plant")
                    pdf.set_font("Times", size=10) 
                    pdf.cell(100, 10, etcp, ln=1)
                    pdf.set_font("Times", size=14) 
                    pdf.set_fill_color(218,230,241)
                    pdf.cell(90, 10, "Tower One Low Rise Fire Pump", fill=True)
                    pdf.set_font("Times", size=10) 
                    pdf.cell(100, 10, etfp1, fill=True, ln=1)
                    pdf.set_font("Times", size=14) 
                    pdf.cell(90, 10, "Tower One High Rise Fire Pump")
                    pdf.set_font("Times", size=10) 
                    pdf.cell(100, 10, etfp2, ln=1)
                    pdf.set_font("Times", size=14) 
                    pdf.set_fill_color(218,230,241)
                    pdf.cell(90, 10, "Tower Two 4-18", fill=True)
                    pdf.set_font("Times", size=10) 
                    pdf.cell(100, 10, wt418, fill=True, ln=1)
                    pdf.set_font("Times", size=14) 
                    pdf.cell(90, 10, "Tower Two 19-31")
                    pdf.set_font("Times", size=10) 
                    pdf.cell(100, 10, wt1931, ln=1)
                    pdf.set_font("Times", size=14) 
                    pdf.set_fill_color(218,230,241)
                    pdf.cell(90, 10, "Tower Two 32-41", fill=True)
                    pdf.set_font("Times", size=10) 
                    pdf.cell(100, 10, wt3241, fill=True, ln=1)
                    pdf.set_font("Times", size=14) 
                    pdf.cell(90, 10, "Tower Two Central Plant")
                    pdf.set_font("Times", size=10) 
                    pdf.cell(100, 10, wtcp, ln=1)
                    pdf.set_font("Times", size=14) 
                    pdf.set_fill_color(218,230,241)
                    pdf.cell(90, 10, "Tower Two Low Rise Fire Pump", fill=True)
                    pdf.set_font("Times", size=10) 
                    pdf.cell(100, 10, wtfp1, fill=True, ln=1)
                    pdf.set_font("Times", size=14) 
                    pdf.cell(90, 10, "Tower Two High Rise Fire Pump")
                    pdf.set_font("Times", size=10) 
                    pdf.cell(100, 10, wtfp2, ln=1)
                    pdf.set_font("Times", size=14) 
                    pdf.set_fill_color(218,230,241)
                    pdf.cell(90, 10, "205-555 8th", fill=True)
                    pdf.set_font("Times", size=10) 
                    pdf.cell(100, 10, om, fill=True, ln=1)
                    pdf.set_font("Times", size=14) 
                    pdf.cell(90, 10, "Amenity Space")
                    pdf.set_font("Times", size=10) 
                    pdf.cell(100, 10, fcv, ln=1)
                    pdf.set_font("Times", size=10) 
                    pdf.cell(48, 10, "Heating Degree Days", border="T")
                    pdf.cell(40, 10, str(HDD) + " / " + str(HDDL), border="T")
                    pdf.cell(48, 10, "Cooling Degree Days", border="T")
                    pdf.cell(40, 10, str(CDD) + " / " + str(CDDL), border="T", ln=1)
                    pdf.cell(48, 10, "Tower One Occupancy")
                    pdf.cell(40, 10, '{:,.0f}'.format(ETO) + " / " + '{:,.0f}'.format(ETOL))  ###For some reason this did not work for April electricity variances
                    pdf.cell(48, 10, "Tower Two Occupancy")
                    pdf.cell(40, 10, '{:,.0f}'.format(WTO) + " / " + '{:,.0f}'.format(WTOL),ln=1)
                    pdf.cell(48, 10, "Amount Contracted")
                    pdf.cell(40, 10, str(contr_value))
                    pdf.cell(48, 10, "Actual Used Amount")
                    pdf.cell(40, 10, str(contracted_use), ln=1)


                    if qreport:
                        pass
                    else:
                        pdf.output(tgt_file)

                   
                    rmonth = s_month_name[0][1]
                    ryear = str(lastyear)
                    rlocation = "first"
                    rvalue = l_et_elec_usage_total
                    rcost = float(l_et_grand_total)
                    s_result = Reading(ryear, rmonth, rlocation, rvalue, rcost)
                    read_list.append(json.dumps(s_result, default=jdefault))
                    rlocation = "second"
                    rvalue = l_wt_elec_usage_total
                    rcost = float(l_wt_grand_total)
                    s_result = Reading(ryear, rmonth, rlocation, rvalue, rcost)
                    read_list.append(json.dumps(s_result, default=jdefault))
                    rlocation = "parkade"
                    rvalue = l_parkade_use
                    rcost = float(l_parkade_cost)
                    s_result = Reading(ryear, rmonth, rlocation, rvalue, rcost)
                    read_list.append(json.dumps(s_result, default=jdefault))
                    ryear = str(yearno)
                    rlocation = "first"
                    rvalue = et_elec_usage_total
                    rcost = float(et_grand_total)
                    s_result = Reading(ryear, rmonth, rlocation, rvalue, rcost)
                    read_list.append(json.dumps(s_result, default=jdefault))
                    rlocation = "second"
                    rvalue = wt_elec_usage_total
                    rcost = float(wt_grand_total)
                    s_result = Reading(ryear, rmonth, rlocation, rvalue, rcost)
                    read_list.append(json.dumps(s_result, default=jdefault))
                    rlocation = "parkade"
                    rvalue = parkade_use
                    rcost = float(parkade_cost)
                    s_result = Reading(ryear, rmonth, rlocation, rvalue, rcost)
                    read_list.append(json.dumps(s_result, default=jdefault))

        else:
            print ("There was absolutely nothing in the database for the current month")

        ###The following will generate a report now that we have determined we're done taking numbers for a multi-month query
        ###This snippet used to be above the else statement, but I moved it down here
        if testctr == months_count:
            if qreport:
                lcount = 1
                pdf1.set_font("Times", size=12) 
                for qq in read_list:
                    q = json.loads(qq)
                    if lcount == 1:
                        pdf1.cell(40, 10, q['rmonth'])
                        pdf1.cell(30, 10, q['ryear'])
                        pdf1.cell(40, 10, str(q['rvalue']) + ": $" + str(q['rcost']))
                        lcount += 1
                    elif lcount == 2:
                        pdf1.cell(40, 10, str(q['rvalue']) + ": $" + str(q['rcost']))
                        lcount += 1
                    elif lcount > 2:
                        pdf1.cell(40, 10, str(q['rvalue']) + ": $" + str(q['rcost']), ln=1)
                        lcount = 1
                pdf1.output(tgt_file2)


       
    elif utility_type == 'water':
        print ("You want water data")
        second_tower_account = "rbt2.wa001"
        first_tower_account = "rbt1.wa001"
        first_amenity_center_account = "rbt1.68020"
        second_amenity_center_account = "rbt2.68020"
        first_parkade_account = "rbt1.wa001"
        second_parkade_account = "rbt2.wa001"
        gst_account = "gs001.001"
        water_cost = []
        et_water_cost = []
        wt_water_cost = []
        water_usage = []
        et_water_usage = []
        wt_water_usage = []
        sewer_cost = []
        et_sewer_cost = []
        wt_sewer_cost = []
        park_sewer_cost = []
        park_water_cost = []
        park_water_usage = []
        total_sum = []
        text2 = "Missing Store3 water meter readingsi\n"
        text3 = "Missing Store2 water meter readings\n"
        text4 = "Missing Store4 water meter readings\n"
        text5 = "Missing Store5 water meter readings\n"
        text6 = "Missing FC level 3 water meter readings\n"
        text7 = "Missing FC level 2 water meter readings\n"
        text8 = "Missing Store6 water meter readings\n"
        text9 = "Missing Tenant1 water meter readings\n"
        text10 = "Missing Tenant2 water meter readings\n"
        text11 = "Missing Tenant3 level 9 water meter readings\n"
        text12 = "Missing Irrigation P1 water meter readings\n"
        text13 = "Missing Irrigation level 3 water meter readings\n"
        text14 = "Missing Tenant4 water meter readings\n"
        text15 = "Missing Tenant5 water meter readings\n"
        text138 = "Missing Tenant6 level 6 water meter readings\n"
        text139 = "Missing Tenant7 15 second water meter readings\n"
        text140 = "Missing Tenant7 18 second water meter readings\n"
        text141 = "Missing Tenant7 20 second water meter readings\n"
        text142 = "Missing Tenant7 25 second water meter readings\n"
        cur = conn.cursor()
        cur.execute("""SELECT tracking_reading.meter_id, usage_amount, usage_cost, transmission_cost, tracking_meter.active FROM tracking_reading, tracking_meter WHERE tracking_reading.meter_id=tracking_meter.id AND tracking_meter.mstype = 'Monthly' AND tracking_meter.mtype = 'Water' AND tracking_reading.month = '%s' AND tracking_reading.year = '%s' """  % (start_month, yearno))
        rows = cur.fetchall()
        if rows:
            for row in rows:
                if row[0] == 152:
                    et_sewer_cost.append(row[3]) 
                    et_water_cost.append(row[2])
                    et_water_usage.append(row[1])
                elif row[0] == 153:
                    et_sewer_cost.append(row[3]) 
                    et_water_cost.append(row[2])
                    et_water_usage.append(row[1])
                elif row[0] == 150:
                    if row[3] == None:
                        pass
                    else:
                        wt_sewer_cost.append(row[3])
                    if row[2] == None:
                        pass
                    else:
                        wt_water_cost.append(row[2])
                    if row[1] == None:
                        pass
                    else:
                        wt_water_usage.append(row[1])
                elif row[0] == 151:
                    if row[3] == None:
                        pass
                    else:
                        wt_sewer_cost.append(row[3])
                    if row[2] == None:
                        pass
                    else:
                        wt_water_cost.append(row[2])
                    if row[1] == None:
                        pass
                    else:
                        wt_water_usage.append(row[1])
                elif row[0] == 154:
                    park_sewer_cost.append(row[3])
                    park_water_cost.append(row[2])
                    park_water_usage.append(row[1])
                elif row[0] == 155:
                    park_sewer_cost.append(row[3])
                    park_water_cost.append(row[2])
                    park_water_usage.append(row[1])
                elif row[0] == 165:
                    if row[4] == 't':
                        c_tenant3_l9 = row[1]
                    else:
                        c_tenant3_l9 = 0
                elif row[0] == 141:
                    c_store3 = row[1]
                    text2 = ""
                elif row[0] == 142:
                    c_store2 = row[1]
                    text3 = ""
                elif row[0] == 143:
                    c_store1 = row[1]
                    text4 = ""
                elif row[0] == 149:
                    c_tenant2 = row[1]
                    text10 = ""
                elif row[0] == 144:
                    c_store5 = row[1]
                    text5 = ""
                elif row[0] == 148:
                    c_tenant1 = row[1]
                    text9 = ""
                elif row[0] == 159:
                    c_tenant5 = row[1]
                    text15 = ""
                elif row[0] ==158:
                    c_tenant4 = row[1]
                    text14 = ""
                elif row[0] == 160:
                    c_tenant6 = row[1]
                    text138 = ""
                elif row[0] == 161:
                    c_cp15w = row[1]
                    text139 = ""
                elif row[0] == 162:
                    c_cp18w = row[1]
                    text140 = ""
                elif row[0] == 163:
                    c_cp20w = row[1]
                    text141 = ""
                elif row[0] == 164:
                    c_cp25w = row[1]
                    text142 = ""
                elif row[0] == 147:
                    c_store6 = row[1]
                    text8 = ""
                elif row[0] == 156:
                    c_parkade_irrigation = row[1]
                    text12 = ""
                elif row[0] == 157:
                    c_green_roof = row[1]
                    text13 = ""
                elif row[0] == 145:
                    c_amenity_main = row[1]
                    text7 = ""
                elif row[0] == 146:
                    c_amenity_handicapped = row[1]
                    text6 = ""

        total_et_water = sum(et_water_cost)
        total_et_sewer = sum(et_sewer_cost)
        total_et_use = sum(et_water_usage)
        et_water_per_unit = total_et_water / total_et_use
        et_sewer_per_unit = total_et_sewer / total_et_use
        ###If we get complaints about NoneType and int not adding up, it means someone has misclassed a daily reading into the monthly category
        total_wt_water = sum(wt_water_cost) or 0
        total_wt_sewer = sum(wt_sewer_cost) or 0
        total_wt_use = sum(wt_water_usage) or 1
        wt_water_per_unit = (total_wt_water / total_wt_use) 
        wt_sewer_per_unit = (total_wt_sewer / total_wt_use) 
        total_park_water = sum(park_water_cost)
        total_park_sewer = sum(park_sewer_cost)
        total_park_use = sum(park_water_usage)

        use_total_et_bill = total_et_use + total_park_use

        park_water_per_unit = total_park_water / total_park_use
        park_sewer_per_unit = total_park_sewer / total_park_use
        et_gross_total_cost = total_et_water + total_et_sewer
        wt_gross_total_cost = total_wt_water + total_wt_sewer
        park_gross_total_cost = total_park_water + total_park_sewer

        print ("The total usage for the first tower is %d" % total_et_use)
        print ("The total water cost for the first tower is %f" % total_et_water)
        print ("The cost per unit for water in the first tower is %f" % et_water_per_unit)
        print ("The total sewer cost for the first tower is %f" % total_et_sewer)
        print ("The cost per unit for sewer in the first tower is %f" % et_sewer_per_unit)
        print ("The overall total cost for the first tower is %f" % et_gross_total_cost)
        print ("############################################################################")
        print ("The total usage for the second tower is %d" % total_wt_use)
        print ("The total water cost for the second tower is %f" % total_wt_water)
        print ("The cost per unit for water in the second tower is %f" % wt_water_per_unit)
        print ("The total sewer cost for the second tower is %f" % total_wt_sewer)
        print ("The cost per unit for sewer in the second tower is %f" % wt_sewer_per_unit)
        print ("The overall total cost for the second tower is %f" % wt_gross_total_cost)
        print ("############################################################################")
        print ("The total usage for the parkade is %d" % total_park_use)
        print ("The total water cost for the parkade is %f" % total_park_water)
        print ("The cost per unit for water in the parkade is %f" % park_water_per_unit)
        print ("The total sewer cost for the parkade is %f" % total_park_sewer)
        print ("The cost per unit for sewer in the parkade is %f" % park_sewer_per_unit)
        print ("The overall total cost for the parkade is %f" % park_gross_total_cost)
        print ("############################################################################")
        print ("\n")

        l_water_cost = []
        l_et_water_cost = []
        l_wt_water_cost = []
        l_water_usage = []
        l_et_water_usage = []
        l_wt_water_usage = []
        l_sewer_cost = []
        l_et_sewer_cost = []
        l_wt_sewer_cost = []
        l_park_sewer_cost = []
        l_park_water_cost = []
        l_park_water_usage = []
        l_total_sum = []

        if start_month == 1:
            lmyear = int(yearno) - 1
        else:
            lmyear = yearno
        ###The below is to get the previous month's readings to calculate tenant meter usage amounts
        cur1 = conn.cursor()
        cur1.execute("""SELECT tracking_reading.meter_id, usage_amount, usage_cost, transmission_cost, tracking_meter.active FROM tracking_reading, tracking_meter WHERE tracking_reading.meter_id=tracking_meter.id AND tracking_meter.mstype = 'Monthly' AND tracking_meter.mtype = 'Water' AND tracking_reading.month = '%s' AND tracking_reading.year = '%s' """  % (prev_month, lmyear))
        rows1 = cur1.fetchall()
        if rows1:
            for row1 in rows1:
                if row1[0] == 152:
                    l_et_sewer_cost.append(row1[3]) 
                    l_et_water_cost.append(row1[2])
                    l_et_water_usage.append(row1[1])
                elif row1[0] == 153:
                    l_et_sewer_cost.append(row1[3]) 
                    l_et_water_cost.append(row1[2])
                    l_et_water_usage.append(row1[1])
                elif row1[0] == 150:
                    l_wt_sewer_cost.append(row1[3])
                    l_wt_water_cost.append(row1[2])
                    l_wt_water_usage.append(row1[1])
                elif row1[0] == 151:
                    l_wt_sewer_cost.append(row1[3])
                    l_wt_water_cost.append(row1[2])
                    l_wt_water_usage.append(row1[1])
                elif row1[0] == 154:
                    l_park_sewer_cost.append(row1[3])
                    l_park_water_cost.append(row1[2])
                    l_park_water_usage.append(row1[1])
                elif row1[0] == 155:
                    l_park_sewer_cost.append(row1[3])
                    l_park_water_cost.append(row1[2])
                    l_park_water_usage.append(row1[1])
                elif row1[0] == 165:
                    if row1[4] == 't':
                        p_tenant3_l9 = row[1]
                    else:
                        p_tenant3_l9 = 0
                elif row1[0] == 141:
                    p_store3 = row1[1]
                elif row1[0] == 142:
                    p_store2 = row1[1]
                elif row1[0] == 143:
                    p_store1 = row1[1]
                elif row1[0] == 149:
                    p_tenant2 = row1[1]
                elif row1[0] == 144:
                    p_store5 = row1[1]
                elif row1[0] == 148:
                    p_tenant1 = row1[1]
                elif row1[0] == 159:
                    p_tenant5 = row1[1]
                elif row1[0] ==158:
                    p_tenant4 = row1[1]
                elif row1[0] == 160:
                    p_tenant6 = row1[1]
                elif row1[0] == 161:
                    p_cp15w = row1[1]
                elif row1[0] == 162:
                    p_cp18w = row1[1]
                elif row1[0] == 163:
                    p_cp20w = row1[1]
                elif row1[0] == 164:
                    p_cp25w = row1[1]
                elif row1[0] == 147:
                    p_store6 = row1[1]
                elif row1[0] == 156:
                    p_parkade_irrigation = row1[1]
                elif row1[0] == 157:
                    p_green_roof = row1[1]
                elif row1[0] == 145:
                    p_amenity_main = row1[1]
                elif row1[0] == 146:
                    p_amenity_handicapped = row1[1]

        ###The following will allow us to convert from gallons to M3 - which has to be done with the parkade irrigation meter
        gal_2_m3 = 0.00378541
        lower_level_irrigation = (c_parkade_irrigation * gal_2_m3) - (p_parkade_irrigation * gal_2_m3)
        green_roof_irrigation = c_green_roof - p_green_roof
        total_irrigation = lower_level_irrigation + green_roof_irrigation
        total_irrigation_cost = (total_irrigation * float(et_water_per_unit)) + (total_irrigation * float(et_sewer_per_unit))
        et_irrigation = total_irrigation * .565
        wt_irrigation = total_irrigation - et_irrigation
        et_irrigation_cost = float(total_irrigation_cost) * .565
        wt_irrigation_cost = float(total_irrigation_cost) - et_irrigation_cost
          
        main_amenity = c_amenity_main - p_amenity_main
        handicapped_amenity = c_amenity_handicapped - p_amenity_handicapped
        total_amenity = main_amenity + handicapped_amenity
        total_amenity_cost = (total_amenity * et_water_per_unit) + (total_amenity * et_sewer_per_unit)
        et_amenity = total_amenity * .565
        wt_amenity = total_amenity - et_amenity
        et_amenity_cost = float(total_amenity_cost) * .565
        wt_amenity_cost = float(total_amenity_cost) - et_amenity_cost

        store3_use = ((c_store3 - p_store3) * 0.01)  ##Convert to M3
        ###I put the below meter to inactive, so now it did not pull the data because of the meter being inactive
        ###Problem: there is no way to differentiate between inactive and no entry made for the month
        ###Possible solution: I may need to still query for all (active and inactive) and then do something based upon that active/inactive value
        tenant3_use = c_tenant3_l9 - p_tenant3_l9
        store2_use = c_store2 - p_store2
        store1_use = c_store1 - p_store1
        store5_use = ((c_store5 - p_store5) * 0.1)
        store6_use = c_store6 - p_store6
        tenant2_use = c_tenant2 - p_tenant2
        tenant1_use = c_tenant1 - p_tenant1
        tenant5_use = c_tenant5 - p_tenant5
        tenant4_use = c_tenant4 - p_tenant4
        tenant6_use = c_tenant6 - p_tenant6
        cp15w_use = c_cp15w - p_cp15w
        cp18w_use = c_cp18w - p_cp18w
        cp20w_use = c_cp20w - p_cp20w
        cp25w_use = c_cp25w - p_cp25w

        store3_cost = (float(store3_use) * float(et_water_per_unit)) + (float(store3_use) * float(et_sewer_per_unit))
        tenant3_cost = (float(tenant3_use) * float(et_water_per_unit)) + (float(tenant3_use) * float(et_sewer_per_unit))
        store2_cost = (float(store2_use) * float(et_water_per_unit)) + (float(store2_use) * float(et_sewer_per_unit))
        store1_cost = (float(store1_use) * float(et_water_per_unit)) + (float(store1_use) * float(et_sewer_per_unit))
        store5_cost = (float(store5_use) * float(et_water_per_unit)) + (float(store5_use) * float(et_sewer_per_unit))
        store6_cost = (float(store6_use) * float(et_water_per_unit)) + (float(store6_use) * float(et_sewer_per_unit))
        tenant2_cost = (float(tenant2_use) * float(et_water_per_unit)) + (float(tenant2_use) * float(et_sewer_per_unit))
        tenant1_cost = (float(tenant1_use) * float(et_water_per_unit)) + (float(tenant1_use) * float(et_sewer_per_unit))
        tenant5_cost = (float(tenant5_use) * float(et_water_per_unit)) + (float(tenant5_use) * float(et_sewer_per_unit))
        tenant4_cost = (float(tenant4_use) * float(et_water_per_unit)) + (float(tenant4_use) * float(et_sewer_per_unit))

        tenant6_cost = (float(tenant6_use) * float(wt_water_per_unit)) + (float(tenant6_use) * float(wt_sewer_per_unit))
        cp15w_cost = (float(cp15w_use) * float(wt_water_per_unit)) + (float(cp15w_use) * float(wt_sewer_per_unit))
        cp18w_cost = (float(cp18w_use) * float(wt_water_per_unit)) + (float(cp18w_use) * float(wt_sewer_per_unit))
        cp20w_cost = (float(cp20w_use) * float(wt_water_per_unit)) + (float(cp20w_use) * float(wt_sewer_per_unit))
        cp25w_cost = (float(cp25w_use) * float(wt_water_per_unit)) + (float(cp25w_use) * float(wt_sewer_per_unit))

        et_parkade_use_share = int(total_park_use) * .565
        wt_parkade_use_share = total_park_use - et_parkade_use_share
        et_parkade_cost_share = float(park_gross_total_cost) * .565
        wt_parkade_cost_share = float(park_gross_total_cost) - et_parkade_cost_share

        bill_one_cost = et_gross_total_cost + park_gross_total_cost
        bill_one_deducts = float(park_gross_total_cost) + float(total_irrigation_cost) + float(store3_cost) + float(store2_cost) + float(store1_cost) + float(store5_cost) + float(total_amenity_cost) + float(store6_cost) + float(tenant1_cost) + float(tenant2_cost) + float(tenant3_cost)
        et_net_cost = float(bill_one_cost) - bill_one_deducts

        bill_two_deducts = float(tenant6_cost) + float(cp15w_cost) + float(cp18w_cost) + float(cp20w_cost) + float(cp25w_cost)
        wt_net_cost = float(wt_gross_total_cost) - bill_two_deducts

        total_tenant_usage = total_park_use + store3_use + tenant3_use + store2_use + store1_use + store5_use + store6_use + tenant2_use + tenant5_use + tenant4_use + tenant1_use + total_amenity + total_irrigation
        et_total_use = use_total_et_bill - int(total_tenant_usage)
        total_wt_tenant_use = tenant6_use + cp15w_use + cp18w_use + cp20w_use + cp25w_use
        wt_net_use = total_wt_use - int(total_wt_tenant_use)
        


        if report_type == 'bill':
            tgt_file = monthname + "-" + yearno + "-" + utility_type + ".pdf"
            if multiples == 0:
                header = utility_type[:1].upper() + utility_type[1:]
                moname = monthname[:1].upper() + monthname[1:]
                theader = moname + " " + yearno + " " + header + " Bill Allocation"
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Times", 'B', 24) 
                cell_width = (len(theader) * 4.3) + 20
                pdf.cell(cell_width, 40, theader, ln=1)
                pdf.set_font("Times", 'U', 14) 
                pdf.cell(70, 10, "Entity")
                pdf.cell(40, 10, "Account Number")
                pdf.cell(40, 10, "Usage Volume")
                pdf.cell(40, 10, "Cost Incurred", ln=1)
                pdf.set_font("Times", size=14) 
                pdf.cell(70, 10, "Tower One Parkade Costs")
                pdf.cell(40, 10, first_parkade_account)
                pdf.cell(40, 10, '{:,.0f}'.format(et_parkade_use_share), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(et_parkade_cost_share), ln=1)
                pdf.cell(70, 10, "Tower Two Parkade Costs")
                pdf.cell(40, 10, second_parkade_account)
                pdf.cell(40, 10, '{:,.0f}'.format(wt_parkade_use_share), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(wt_parkade_cost_share), ln=1)
                pdf.cell(70, 10, "Tower One Irrigation Costs")
                pdf.cell(40, 10, first_tower_account)
                pdf.cell(40, 10, '{:,.0f}'.format(et_irrigation), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(et_irrigation_cost), ln=1)
                pdf.cell(70, 10, "Tower Two Irrigation Costs")
                pdf.cell(40, 10, second_tower_account)
                pdf.cell(40, 10, '{:,.0f}'.format(wt_irrigation), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(wt_irrigation_cost), ln=1)
                pdf.cell(70, 10, "Store3")
                pdf.cell(40, 10, first_tower_account)
                pdf.cell(40, 10, '{:,.0f}'.format(store3_use), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(store3_cost), ln=1)
                pdf.cell(70, 10, "Store2")
                pdf.cell(40, 10, first_tower_account)
                pdf.cell(40, 10, '{:,.0f}'.format(store2_use), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(store2_cost), ln=1)
                pdf.cell(70, 10, "Store4")
                pdf.cell(40, 10, first_tower_account)
                pdf.cell(40, 10, '{:,.0f}'.format(store1_use), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(store1_cost), ln=1)
                pdf.cell(70, 10, "Store5")
                pdf.cell(40, 10, first_tower_account)
                pdf.cell(40, 10, '{:,.0f}'.format(store5_use), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(store5_cost), ln=1)
                pdf.cell(70, 10, "Tower One Fitness Ctr Costs")
                pdf.cell(40, 10, first_amenity_center_account)
                pdf.cell(40, 10, '{:,.0f}'.format(et_amenity), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(et_amenity_cost), ln=1)
                pdf.cell(70, 10, "Tower Two Fitness Ctr Costs")
                pdf.cell(40, 10, second_amenity_center_account)
                pdf.cell(40, 10, '{:,.0f}'.format(wt_amenity), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(wt_amenity_cost), ln=1)
                pdf.cell(70, 10, "Store6")
                pdf.cell(40, 10, first_tower_account)
                pdf.cell(40, 10, '{:,.0f}'.format(store6_use), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(store6_cost), ln=1)
                pdf.cell(70, 10, "Richardson GMP")
                pdf.cell(40, 10, first_tower_account)
                pdf.cell(40, 10, '{:,.0f}'.format(tenant1_use), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(tenant1_cost), ln=1)
                pdf.cell(70, 10, "Tenant2")
                pdf.cell(40, 10, first_tower_account)
                pdf.cell(40, 10, '{:,.0f}'.format(tenant2_use), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(tenant2_cost), ln=1)
                pdf.cell(70, 10, "Tenant3")
                pdf.cell(40, 10, first_tower_account)
                pdf.cell(40, 10, '{:,.0f}'.format(tenant3_use), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(tenant3_cost), ln=1)
                pdf.cell(70, 10, "Tower One Costs")
                pdf.cell(40, 10, first_tower_account)
                pdf.cell(40, 10, str(et_total_use), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(et_net_cost), ln=1)
                pdf.cell(110, 10, "Totals", border="T")
                pdf.cell(40, 10, str(use_total_et_bill), border="T", align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(bill_one_cost), border="T")
                    
                pdf.add_page()
                pdf.set_font("Times", 'B', 24) 
                celpm_width = (len(theader) * 4.3) + 20
                pdf.cell(celpm_width, 40, theader, ln=1)
                pdf.set_font("Times", 'U', 14) 
                pdf.cell(70, 10, "Entity")
                pdf.cell(40, 10, "Account Number")
                pdf.cell(40, 10, "Usage Volume")
                pdf.cell(40, 10, "Cost Incurred", ln=1)
                pdf.set_font("Times", size=14) 
                pdf.cell(70, 10, "Tenant6")
                pdf.cell(40, 10, second_tower_account)
                pdf.cell(40, 10, '{:,.0f}'.format(tenant6_use), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(tenant6_cost), ln=1)
                pdf.cell(70, 10, "Tenant7 Level 15")
                pdf.cell(40, 10, second_tower_account)
                pdf.cell(40, 10, '{:,.0f}'.format(cp15w_use), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(cp15w_cost), ln=1)
                pdf.cell(70, 10, "Tenant7 Level 18")
                pdf.cell(40, 10, second_tower_account)
                pdf.cell(40, 10, '{:,.0f}'.format(cp18w_use), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(cp18w_cost), ln=1)
                pdf.cell(70, 10, "Tenant7 Level 20")
                pdf.cell(40, 10, second_tower_account)
                pdf.cell(40, 10, '{:,.0f}'.format(cp20w_use), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(cp20w_cost), ln=1)
                pdf.cell(70, 10, "Tenant7 Level 25")
                pdf.cell(40, 10, second_tower_account)
                pdf.cell(40, 10, '{:,.0f}'.format(cp25w_use), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(cp25w_cost), ln=1)
                pdf.cell(70, 10, "Tower Two Costs")
                pdf.cell(40, 10, second_tower_account)
                pdf.cell(40, 10, str(wt_net_use), align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(wt_net_cost), ln=1)

                pdf.cell(110, 10, "Totals", border="T")
                pdf.cell(40, 10, str(total_wt_use), border="T", align="C")
                pdf.cell(40, 10, '${:,.2f}'.format(wt_gross_total_cost), border="T")

                pdf.output(tgt_file)
            else:
                pass

        elif variance:
            ###Get the current year month billing usages
            cur.execute("""SELECT tracking_reading.meter_id, usage_amount, usage_cost, transmission_cost, tracking_meter.active FROM tracking_reading, tracking_meter WHERE tracking_reading.meter_id=tracking_meter.id AND tracking_meter.mstype = 'Monthly' AND tracking_meter.mtype = 'Water' AND tracking_reading.month = '%s' AND tracking_reading.year = '%s' """  % (start_month, yearno))
            rows = cur.fetchall()
            if rows:
                for row in rows:
                    if row[0] == 150:
                        wt1_usage = row[1]
                        wt1_cost = row[2] + row[3]
                    elif row[0] == 151:
                        wt2_usage = row[1]
                        wt2_cost = row[2] + row[3]
                    elif row[0] == 152:
                        et1_usage = row[1]
                        et1_cost = row[2] + row[3]
                    elif row[0] == 153:
                        et2_usage = row[1]
                        et2_cost = row[2] + row[3]
                    elif row[0] == 154:
                        parkade1_usage = row[1]
                        parkade1_cost = row[2] + row[3]
                    elif row[0] == 155:
                        parkade2_usage = row[1]
                        parkade2_cost = row[2] + row[3]
                    else:
                        pass

            ###Get last year's data
            curr.execute("""SELECT tracking_reading.meter_id, usage_amount, usage_cost, transmission_cost, tracking_meter.active FROM tracking_reading, tracking_meter WHERE tracking_reading.meter_id=tracking_meter.id AND tracking_meter.mstype = 'Monthly' AND tracking_meter.mtype = 'Water' AND tracking_reading.month = '%s' AND tracking_reading.year = '%s' """  % (start_month, lastyear))
            rows1 = curr.fetchall()
            if rows1:
                for row1 in rows1:
                    if row1[0] == 150:
                        l_wt1_usage = row1[1]
                        l_wt1_cost = row1[2] + row1[3]
                    elif row1[0] == 151:
                        l_wt2_usage = row1[1]
                        l_wt2_cost = row1[2] + row1[3]
                    elif row1[0] == 152:
                        l_et1_usage = row1[1]
                        l_et1_cost = row1[2] + row1[3]
                    elif row1[0] == 153:
                        l_et2_usage = row1[1]
                        l_et2_cost = row1[2] + row1[3]
                    elif row1[0] == 154:
                        l_parkade1_usage = row1[1]
                        l_parkade1_cost = row1[2] + row1[3]
                    elif row1[0] == 155:
                        l_parkade2_usage = row1[1]
                        l_parkade2_cost = row1[2] + row1[3]
                    else:
                        pass
            
            ###Below here we'll need to put together the comparison charts


    else:
        print ("You must've put something in wrong.  Try again.")
        sys.exit(1)

send_it(tgt_file)

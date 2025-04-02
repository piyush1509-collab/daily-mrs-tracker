from flask import Flask, render_template, request, jsonify
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)

# Google Sheets API Setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)  # ✅ Define `client` properly
SPREADSHEET_NAME = "items"
sh = client.open(SPREADSHEET_NAME)

# Open necessary sheets
inventory_sheet = sh.worksheet("Inventory")
consumption_sheet = sh.worksheet("Consumption Log")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/mrs')
def mrs():
    return render_template('mrs.html')

@app.route('/tools')
def tools():
    return render_template('tools.html')

@app.route('/store')
def store():
    return render_template('store.html')

@app.route('/user')
def user():
    return render_template('user.html')

# API to get items from inventory
@app.route('/get-item-names', methods=['GET'])
def get_item_names():
    try:
        inventory_sheet = sh.worksheet("Inventory")
        inventory_data = inventory_sheet.get_all_records()
        item_names = [row["Item Name"] for row in inventory_data]
        return jsonify(item_names)
    except Exception as e:
        print("Error fetching item names:", str(e))
        return jsonify({"error": str(e)}), 500


# API to get consumption history
@app.route('/consumption-history', methods=['GET'])
def get_consumption_history():
    try:
        records = consumption_sheet.get_all_records()
        print("Fetched Consumption Records:", records)  # Debugging line

        # Extract query parameters
        area_filter = request.args.get("area", "").strip()
        date_filter = request.args.get("date", "").strip()

        # Check if column names are correct
        if not records or "Consumed Area" not in records[0] or "Date" not in records[0]:
            return jsonify({"error": "Column names mismatch in Google Sheet"}), 500

        # Filter records based on area & date
        filtered_records = [
            record for record in records
            if (not area_filter or record.get("Consumed Area", "").strip() == area_filter)
            and (not date_filter or record.get("Date", "").strip() == date_filter)
        ]

        print("Filtered Consumption Records:", filtered_records)  # Debugging
        return jsonify(filtered_records)

    except Exception as e:
        print("Error fetching consumption history:", str(e))
        return jsonify({"error": str(e)}), 500


# Log Tool Entry (Default: Pending Status)
@app.route('/log-tool', methods=['POST'])
def log_tool():
    try:
        data = request.json
        tool_entry = [
            data["Tool Name"], data["Area"], data["In-Charge"],
            data["Receiver Name"], data["Contractor Name"],
            data["Date Issued"], "Pending"
        ]
        
        log_sheet = sh.worksheet("Tools & Safety Log")
        pending_sheet = sh.worksheet("Tools Pending")
        
        log_sheet.append_row(tool_entry)
        pending_sheet.append_row(tool_entry)  # Also add to pending tools
        
        return jsonify({"message": "Tool logged successfully!"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Modify Tool Status
@app.route('/modify-tool-status', methods=['POST'])
def modify_tool_status():
    try:
        data = request.json
        tool_name = data["Tool Name"]
        status = data["Status"]
        return_date = data.get("Return Date", "")  # Get return date or empty if not provided

        log_sheet = sh.worksheet("Tools & Safety Log")
        pending_sheet = sh.worksheet("Tools Pending")

        # Update status & return date in Tools & Safety Log
        records = log_sheet.get_all_records()
        for i, record in enumerate(records, start=2):
            if record["Tool Name"] == tool_name and record["Status"] == "Pending":
                log_sheet.update(f"G{i}", [[status]])  # Column G is "Status"
                log_sheet.update(f"H{i}", [[return_date]])  # Column H is "Return Date"
                break
        
        # Remove from Tools Pending if status is "Returned"
        if status == "Returned":
            pending_records = pending_sheet.get_all_records()
            for i, record in enumerate(pending_records, start=2):
                if record["Tool Name"] == tool_name:
                    pending_sheet.delete_rows(i)
                    break
        
        return jsonify({"message": "Tool status updated successfully!"})
    except Exception as e:
        print("Error modifying tool status:", str(e))
        return jsonify({"error": str(e)}), 500

# Fetch Pending Tools
@app.route('/get-pending-tools', methods=['GET'])
def get_pending_tools():
    try:
        sheet = sh.worksheet("Tools Pending")
        records = sheet.get_all_records()

        # Debugging: Print the API response
        print("Pending Tools Data:", records)

        return jsonify(records if isinstance(records, list) else [])
    except Exception as e:
        return jsonify({"error": str(e)}), 500



# Fetch Tools Inventory for Suggestions
def fetch_tools_inventory():
    sheet = sh.worksheet("Tools Inventory")
    records = sheet.get_all_records()
    return [record["Tool Name"] for record in records if "Tool Name" in record]

@app.route('/get-tools', methods=['GET'])
def get_tools():
    try:
        sheet = sh.worksheet("Tools Inventory")  # Ensure "Tools Inventory" exists in your spreadsheet
        tools = sheet.col_values(1)[1:]  # Get all tool names (skip header)
        return jsonify(tools)
    except Exception as e:
        print("Error fetching tool names:", str(e))
        return jsonify({"error": str(e)}), 500
        
@app.route('/log-consumption-page')
def log_consumption_page():
    return render_template('log_consumption.html')

@app.route('/view-consumption-page')
def view_consumption_page():
    return render_template('view_consumption.html')


@app.route('/log-consumption', methods=['POST'])
def log_consumption():
    try:
        data = request.json
        items = data.get("items", [])

        if not items:
            return jsonify({"error": "No items provided!"}), 400

        consumed_area = data["Consumed Area"]
        shift = data["Shift"]
        date = data["Date"]
        area_incharge = data["Area-Incharge"]
        receiver = data["Receiver"]
        contractor = data["Contractor"]

        inventory_data = inventory_sheet.get_all_records()

        for item in items:
            item_code = str(item["Item Code"]).strip()
            item_name = item["Item Name"]
            quantity = int(item["Quantity"])
            unit = item["Unit"]

            # Find item in inventory
            found = False
            for idx, row in enumerate(inventory_data):
                if str(row["Item Code"]).strip() == item_code:
                    found = True
                    physical_stock = int(row["Physical Stock"])

                    if physical_stock < quantity:
                        return jsonify({"error": f"Insufficient stock for {item_name} ({item_code})!"}), 400
                    
                    # Update stock
                    new_stock = max(0, physical_stock - quantity)
                    inventory_sheet.update_cell(idx + 2, 3, new_stock)
                    break  # Stop searching after finding the item
            
            if not found:
                return jsonify({"error": f"Item {item_name} ({item_code}) not found in inventory!"}), 400

            # Log the consumption entry
            log_entry = [date, item_name, item_code, quantity, unit, consumed_area, shift, area_incharge, receiver, contractor]
            consumption_sheet.append_row(log_entry)

        return jsonify({"message": "All items logged successfully!"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/AP-item-stocklist')
def ap_item_stocklist():
    return render_template('AP-item-stocklist')

@app.route('/inventory-stock-list')
def inventory_stock_list():
    return render_template('inventory_stock_list.html')

@app.route('/add-inventory', methods=['GET', 'POST'])
def add_inventory_page():
    if request.method == 'GET':
        return render_template('add_inventory.html')  # Serve the HTML page

    elif request.method == 'POST':
        try:
            data = request.json
            item_code = str(data["Item Code"])
            item_name = data["Item Name"]
            qty_added = int(data["QTY Added"])
            date_added = data["Date"]
            location = data["Receiving Location"]

            inventory_sheet = sh.worksheet("Inventory")
            inventory_data = inventory_sheet.get_all_records()

            # Update physical stock in Inventory sheet
            for i, row in enumerate(inventory_data):
                if str(row["Item Code"]) == item_code:
                    new_stock = int(row["Physical Stock"]) + qty_added
                    inventory_sheet.update_cell(i+2, 3, new_stock)  # Assuming "Physical Stock" is column 3
                    break

            # Log the added stock in MOT sheet
            mot_sheet = sh.worksheet("MOT")
            mot_entry = [item_code, item_name, qty_added, date_added, location]
            mot_sheet.append_row(mot_entry)

            return jsonify({"message": "Stock successfully added!"})

        except Exception as e:
            print("Error adding stock:", str(e))
            return jsonify({"error": str(e)}), 500

@app.route('/view-low-stock')
def view_low_stock():
    return render_template('view_low_stock.html')
@app.route('/new-area-wise-consumption', methods=['GET'])
def new_area_wise_consumption():
    try:
        start_date = request.args.get('start_date', '').strip()
        end_date = request.args.get('end_date', '').strip()

        records = consumption_sheet.get_all_records()
        filtered_records = []

        for record in records:
            record_date = record.get("Date", "").strip()
            if start_date <= record_date <= end_date:
                filtered_records.append(record)

        # Group by Area and Sum Consumption
        consumption_data = {}
        for record in filtered_records:
            area = record.get("Consumed Area", "").strip()
            quantity = int(record.get("Quantity", 0))

            if area in consumption_data:
                consumption_data[area] += quantity
            else:
                consumption_data[area] = quantity

        return jsonify(consumption_data)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/Consumption-Report')
def consumption_report_page():
    return render_template('Consumption-Report.html')  # Ensure the file exists

@app.route('/area-wise-consumption')
def area_wise_consumption():
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        item_name = request.args.get('item', '').strip().lower()

        consumption_sheet = sh.worksheet("Consumption Log")
        consumption_data = consumption_sheet.get_all_records()

        filtered_data = {}
        for row in consumption_data:
            if start_date and row["Date"] < start_date:
                continue
            if end_date and row["Date"] > end_date:
                continue
            if item_name and item_name not in row["Item name"].strip().lower():
                continue

            area = row["Consumed Area"]
            qty = int(row["Quantity"])
            filtered_data[area] = filtered_data.get(area, 0) + qty

        return jsonify(filtered_data)

    except Exception as e:
        print("Error fetching consumption data:", str(e))
        return jsonify({"error": str(e)}), 500
        
@app.route('/get-inventory', methods=['GET'])
def get_inventory():
    try:
        inventory_sheet = sh.worksheet("Inventory")
        inventory_data = inventory_sheet.get_all_records()
        return jsonify(inventory_data)
    except Exception as e:
        print("Error fetching inventory stock:", str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/check-stock', methods=['GET'])
def check_stock():
    try:
        item_code = request.args.get("itemCode")

        # ✅ Open the Inventory sheet
        inventory_sheet = sh.worksheet("Inventory")
        inventory_data = inventory_sheet.get_all_records()

        # ✅ Find the item in Inventory
        for row in inventory_data:
            if str(row["Item Code"]) == str(item_code):
                return jsonify({
                    "Item Code": item_code,
                    "Physical Stock": row.get("Physical Stock", 0),
                    "Minimum Stock": row.get("Minimum Stock", 0)
                })

        return jsonify({"error": "Item not found"}), 404
    except Exception as e:
        print("Error checking stock:", str(e))
        return jsonify({"error": str(e)}), 500
@app.route('/get-low-stock', methods=['GET'])
def get_low_stock():
    try:
        inventory_sheet = sh.worksheet("Inventory")
        inventory_data = inventory_sheet.get_all_records()

        low_stock_items = []
        for item in inventory_data:
            try:
                physical_stock = int(item.get("Physical Stock", 0))
                min_stock = int(item.get("Minimum Stock", 0))

                if physical_stock < min_stock:
                    low_stock_items.append(item)
            except ValueError:
                print(f"Skipping invalid stock data: {item}")

        return jsonify(low_stock_items)
    except Exception as e:
        print("Error fetching low stock items:", str(e))
        return jsonify({"error": str(e)}), 500
        
@app.route('/inventory')
def inventory_page():
    return render_template('inventory.html')

# Run the Flask app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000, debug=True)

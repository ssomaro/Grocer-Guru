# Importing required functions 
from distutils.log import debug 
from fileinput import filename 
from flask import *  
import json
import base64
import requests
import os
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import pandas as pd
import plotly.express as px
import plotly.io as pio
import plotly.graph_objects as go
import logging
import flask_cors
import fitz  # PyMuPDF
from io import BytesIO
from PIL import Image
import io
global global_df 
global_df = None 
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")
app = Flask(__name__)
app.logger.setLevel(logging.DEBUG)
flask_cors.CORS(app)

def encode_image(image_path):
  with open(image_path, "rb") as image_file:
    return base64.b64encode(image_file.read()).decode('utf-8')

def get_data_from_image(image):
    global global_df 
    
    base64_image = image
    headers = {  "Content-Type": "application/json","Authorization": f"Bearer {OPENAI_API_KEY}"}
    payload = {
    "model": "gpt-4-turbo",
    "messages": [
        {
        "role": "user",
        "content": [
            {
            "type": "text",
            "text": ''' Please extract the following information from the receipt: the item bought, its upc and a link ( the method to geneate the is link is given below) 
            and output the information in a structured json format. The receipt is attached below.the link can be generate by using this example if the item name is 'Kroger Grade A Large White Eggs' and upc is UPC: 0001111060933 
            the link is 'https://www.kroger.com/p/kroger-grade-a-large-white-eggs/0001111060933?searchType=suggestions'. give proper json dont give any '\n' in the json
            the json format is 
            {
    "items": [
        {
        "name": "name1",
        "upc": "upc1",
        "link": "https://www.kroger.com/p/ make appropriate link"
        },
        {
        "name": "name2",
        "upc": "upc2",
        "link": "https://www.kroger.com/p/ make appropriate link"
        }
        ]
        }
        dont give any other text just the json no other text and close the json properly
            '''
            },
            {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{base64_image}"
            }
            }
        ]
        }
    ],
    "max_tokens": 2000
    }
    
    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    print(response.json())
    items_json = response.json()['choices'][0]['message']['content']
    
    items = json.loads(items_json)
    print(items)
    upc_list = [item["upc"] for item in items["items"]]
    name_list = [item["name"] for item in items["items"]]
    
    data = []
      # Create a new client and connect to the server
    client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
    
    # Specify the database and collection
    db = client["nutritionalValue"]
    collection = db["scrapedData_v2"]
    
    for upc in upc_list:
        query_result = collection.find_one({"UPC": upc})
        if query_result:
            data.append(query_result)
    global_df = pd.DataFrame(data)
    columns_to_convert = ['Calories', 'Total Fat (g)', 'Cholesterol (mg)', 'Total Carbohydrate (g)', 'Dietary Fiber (g)', 'Sugar (g)', 'Protein (g)', 'Sodium (mg)']
    global_df = convert_columns_to_numeric(global_df, columns_to_convert)
    global_df.to_csv('data.csv', index=False)
    
    return items
def convert_columns_to_numeric(df, columns):
    for col in columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    return df


@app.route('/submit', methods=['GET', 'POST'])
def submit():
    if request.method == 'POST' :
        f = request.files['file'] 
        print(f)
        try:
            doc = fitz.open("pdf", f.read())
            if len(doc) == 1:
                page = doc[0]  # Get the first and only page
                pix = page.get_pixmap()  # Render page to an image
                
                # Convert the pixmap to an image file like object using Pillow
                img = Image.open(BytesIO(pix.tobytes("png")))
                
                # Save the image to a bytes buffer instead of disk
                img_bytes = BytesIO()
                img.save(img_bytes, format='PNG')
                img_bytes.seek(0)
                  # Save image as PNG
            else:
                return "Error: PDF should contain exactly one page"
            doc.close()
            # images = convert_from_bytes(f.read())
            # first_image = images[0]
        except Exception as e:
            app.logger.error(f"Error processing the image: {str(e)}")
            return str(e), 500 
        # buffered = io.BytesIO()
        # first_image.save(buffered, format="JPEG")
        img_bytes.seek(0) 
        img_base64 = base64.b64encode(img_bytes.read()).decode('utf-8')
        # img_str = base64.b64encode(buffered.getvalue()).decode()
        # images[0].save('page1' +'.jpg', 'JPEG')
        get_data_from_image(img_base64)
        # global global_df
        # global_df = pd.read_csv('data.csv')
        # render_template('plots.html')
        return render_template('plots.html')

@app.route('/get_summary_text')
def get_summary():
    global global_df 
    ddf = global_df
    text_table = ddf.to_string(index=False)
   
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }
    payload = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {
            "role": "user",
            "content":f''' The following is a content of nutritional values for various food items:\n\n{text_table}\n\nPlease provide a summary of items. be specific and mention items.
              an example summay gives an one line overview on how health the items are and then commention on few nutriients that are in excessive or are lacking and make few specific recommendations"
              keep in mind that this is an executive summary of an app that analyses the grocery items of a person and provides a summary of the nutritional values of the items in the grocery list.
              dont be generic. it is a executive summary keep it professional and it is the start of the webpage so it should be engaging and informative. give one whole paragraph of summary, dont mention "product name not found"
            '''
            }
        ],
        "max_tokens": 2000
    }

    # API request
    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)

    # Extract and print the JSON response
    items_json = response.json()
    
    summary  =  '''{"summary": "The grocery items in your list are a mix of healthy and unhealthy choices. While some items are high in calories and fat, others are rich in protein and fiber. You should consider reducing your intake of sugar and sodium, and increase your consumption of fiber and protein. For example, you could swap out sugary snacks for fresh fruits and vegetables, and choose lean protein sources like chicken or fish. Overall, your grocery list could benefit from more variety and balance to improve your overall health and well-being."}'''
    # summary = items_json['choices'][0]['message']['content']
    return jsonify(summary)


@app.route('/plots')
def index():
    return render_template('plots.html')

@app.route('/nutritional_summary')
def nutritional_summary():
    global global_df 
    ddf =global_df
    # Get the aggregated data similar to the pie chart
    aggregated_values = ddf[['Calories', 'Total Fat (g)', 'Cholesterol (mg)','Total Carbohydrate (g)', 'Dietary Fiber (g)', 'Sugar (g)', 'Protein (g)','Sodium (mg)',]].sum()
    # Convert it into a list of dictionaries
    nutrients = [{'nutrient': nutrient, 'amount': float(amount)} for nutrient, amount in aggregated_values.items()]
    return jsonify(nutrients)

@app.route('/raw_data')
def raw_data():
    global global_df 
    df = global_df[[ 'product_name','Calories', 'Total Fat (g)',
       'Saturated Fat (g)', 'Trans Fat (g)', 'Cholesterol (mg)', 'Sodium (mg)',
       'Total Carbohydrate (g)', 'Dietary Fiber (g)', 'Sugar (g)',
       'Added Sugar (g)', 'Protein (g)', 'Calcium (mg)', 'Iron (mg)',
       'Potassium (mg)', 'Vitamin D (mcg)', 'Folic Acid (mcg)', 'Niacin (%)',
       'Phosphorus (%)', 'Thiamin (%)', 'Vitamin A (%)', 'Vitamin C (%)',
       'Zinc (%)']]
    return render_template('raw_data.html', tables=[df.to_html(classes='data', header="true")])


@app.route('/', methods=['GET', 'POST'])
def homepage():
    return render_template('home.html')

@app.route('/about', methods=['GET', 'POST'])
def aboutpage():
    return render_template('about.html')


@app.route('/macros_pie_chart')
def macros_pie_chart():
    global global_df 
    if global_df is None:
        return jsonify({"error": "Data not loaded yet"})

    # Convert columns to numeric, assuming they might be read as strings
    numeric_columns = ['Total Fat (g)', 'Saturated Fat (g)', 'Trans Fat (g)',
                       'Total Carbohydrate (g)', 'Dietary Fiber (g)', 'Sugar (g)',
                       'Added Sugar (g)', 'Protein (g)']
    for col in numeric_columns:
        global_df[col] = pd.to_numeric(global_df[col], errors='coerce')

    # Calculate the sum of the nutritional data
    macros = global_df[numeric_columns].sum().reset_index()
    macros.columns = ['Nutrient', 'Value']

    # Define pull-out values for pie chart slices
    pull_values = [0.1 if nutrient != 'Total Fat (g)' else 0.2 for nutrient in macros['Nutrient']]

    # Create the figure using Plotly Graph Objects
    fig = go.Figure(data=[go.Pie(labels=macros['Nutrient'], values=macros['Value'],
                                 pull=pull_values, textinfo='percent+label')])
    
    # Update layout and title
    fig.update_layout(title="Macronutrient Composition of Food Items", showlegend=False)
  
    # Return the figure as JSON
    return jsonify(pio.to_json(fig))




@app.route('/top_calories_bar')
def top_calories_bar():
    global global_df 
    ddf = global_df
    top_calories = ddf.nlargest(3, 'Calories')
    # Melt the DataFrame to long format for Plotly, excluding 'Sodium (mg)'
    top_calories_long = pd.melt(top_calories, id_vars=['product_name'], value_vars=[
        'Total Fat (g)',   'Total Carbohydrate (g)', 'Dietary Fiber (g)', 'Sugar (g)', 'Protein (g)'
    ], var_name='Nutrient', value_name='Amount')
    fig = px.bar(top_calories_long, x='Amount', y='product_name', color='Nutrient', orientation='h',
                 title="Top 3 Calorie-Rich Foods by Nutrient Composition")
    fig.update_layout(title="Top 3 Calorie-Rich Foods by Nutrient Composition", xaxis_title="Quantity", yaxis_title="Product Name")
    return jsonify(fig.to_json())

@app.route('/top_protein_bar')
def top_protein_bar():
    global global_df 
    ddf =global_df
    top_protein = ddf.nlargest(3, 'Protein (g)')
    # Melt the DataFrame to long format for Plotly, excluding 'Sodium (mg)'
    top_protein_long = pd.melt(top_protein, id_vars=['product_name'], value_vars=[
        'Total Fat (g)', 'Total Carbohydrate (g)', 'Dietary Fiber (g)', 'Sugar (g)', 'Protein (g)'
    ], var_name='Nutrient', value_name='Amount')
    fig = px.bar(top_protein_long, x='Amount', y='product_name', color='Nutrient', orientation='h',
                 title="Top 3 Protein-Rich Foods by Nutrient Composition")
    fig.update_layout(title="Top 3 Protein-Rich Foods by Nutrient Composition", xaxis_title="Quantity", yaxis_title="Product Name")
    return jsonify(fig.to_json())


@app.route('/additional_data')
def additional_data():
    global global_df
    if global_df is None:
        return jsonify({"error": "Data not loaded yet"})
    
    # Convert DataFrame to JSON
    data = global_df.to_json(orient="records")
    return jsonify(json.loads(data))

# Main Driver Function 
if __name__ == '__main__':
    app.run(debug=True)

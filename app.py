from flask import Flask, request, render_template_string, session
import os
from prompt import handle_query, ONBOARDING_MESSAGE

app = Flask(__name__)
app.secret_key = os.urandom(24)  # For session management

# get template from template.html file
with open("template.html", "r", encoding="utf-8") as file:
    HTML_TEMPLATE = file.read()

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, onboard_message=ONBOARDING_MESSAGE)

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    query = data.get('query', '')
    response = handle_query(query)
    return {'response': response}

if __name__ == '__main__':
    app.run(debug=True)

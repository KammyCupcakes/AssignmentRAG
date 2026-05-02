from flask import Flask, request, render_template_string, session
import os
from prompt import handle_query

app = Flask(__name__)
app.secret_key = os.urandom(24)  # For session management

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>UMass Boston Campus Navigation Chatbot</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #003366; color: white; margin: 0; padding: 20px; }
        .container { max-width: 600px; margin: auto; background-color: white; color: #003366; padding: 20px; border-radius: 8px; }
        #chat { height: 300px; overflow-y: auto; border: 1px solid #003366; padding: 10px; margin-bottom: 10px; }
        input[type="text"] { width: 80%; padding: 10px; }
        button { padding: 10px; background-color: #003366; color: white; border: none; cursor: pointer; }
    </style>
</head>
<body>
    <div class="container">
        <h1>UMass Boston Campus Navigation Chatbot</h1>
        <p>Hello, I am your assistant for transportation at UMass Boston. I can help with questions about commuting, parking, biking, and walking routes.</p>
        <div id="chat"></div>
        <form id="chat-form">
            <input type="text" id="user-input" placeholder="Ask a question..." required>
            <button type="submit">Send</button>
        </form>
    </div>
    <script>
        const chat = document.getElementById('chat');
        const form = document.getElementById('chat-form');
        const input = document.getElementById('user-input');

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const message = input.value;
            input.value = '';
            chat.innerHTML += `<div class="message user">${message}</div>`;
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: message })
            });
            const data = await response.json();
            chat.innerHTML += `<div class="message assistant">${data.response}</div>`;
            chat.scrollTop = chat.scrollHeight;
        });
    </script>
    <style>
    body { font-family: Arial, sans-serif; background-color: #003366; color: white; margin: 0; padding: 20px; }

    .container {
        max-width: 600px;
        margin: auto;
        background-color: white;
        color: #003366;
        padding: 20px;
        border-radius: 8px;
    }

    #chat {
        height: 300px;
        overflow-y: auto;
        border: 1px solid #003366;
        padding: 10px;
        margin-bottom: 10px;
        display: flex;
        flex-direction: column;
        gap: 10px;
    }

    .message {
        max-width: 70%;
        padding: 10px;
        border-radius: 15px;
        word-wrap: break-word;
    }

    .user {
        align-self: flex-end;
        background-color: #e0e0e0; /* gray bubble */
        color: black;
        border-bottom-right-radius: 0;
    }

    .assistant {
        align-self: flex-start;
        background-color: #003366;
        color: white;
        border-bottom-left-radius: 0;
    }

    input[type="text"] {
        width: 80%;
        padding: 10px;
    }

    button {
        padding: 10px;
        background-color: #003366;
        color: white;
        border: none;
        cursor: pointer;
    }
</style>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    query = data.get('query', '')
    response = handle_query(query)
    return {'response': response}

if __name__ == '__main__':
    app.run(debug=True)

import requests

payload = {
"webhookUrl": "url", 
"webhookUrlToken": "token", 
"markIncomingMessagesReaded": "no", 
"outgoingWebhook": "yes", 
"outgoingMessageWebhook": "yes", 
"incomingWebhook": "yes", 
"outgoingAPIMessageWebhook": "yes"
}
headers = {
    'Content-Type': 'application/json'
}

response = requests.post(url, json=payload)

print(response.text.encode('utf8'))
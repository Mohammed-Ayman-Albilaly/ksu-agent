# Chat API contract

POST /chat

request:  { message, session_id }
response: { answer, citations: [ { title, article, url } ] }

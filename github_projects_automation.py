import os
import requests
from dotenv import load_dotenv

# Carrega variáveis do .env
load_dotenv()
TOKEN = os.getenv("GITHUB_TOKEN")
API_URL = "https://api.github.com/graphql"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# Exemplo de consulta GraphQL (substitua pelos dados do seu projeto)
query = """
{
  viewer {
    login
  }
}
"""

response = requests.post(API_URL, json={"query": query}, headers=headers)
print(response.json())
print(response.text)
import requests
import time
import os

# Função para obter a hora correta via API
def get_time():
    url = "https://script.google.com/macros/s/AKfycbyd5AcbAnWi2Yn0xhFRbyzS4qMq1VucMVgVvhul5XqS9HkAyJY/exec?tz=Brazil/East"  # Você pode alterar o fuso horário
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        return data
    else:
        print("Erro ao obter a hora!")
        return None

# Função para atualizar o sistema com a hora
def set_system_time():
    current_time = get_time()
    if current_time:
        
        # Extraindo horas, minutos e segundos
        hours = current_time["hours"]
        minutes = current_time["minutes"]
        seconds =  current_time["seconds"]

        #day = current_time["day"]
        #month = current_time["month"]
        #year = current_time["year"]
        
        # Comando para setar a hora no Windows
        os.system(f"time {hours}:{minutes}:{seconds}")
        #os.system(f"date {day}/{month}/{year}")

# Chamada para ajustar a hora
set_system_time()

# evplug-mobile-server

# Serveur d'application mobile

## Description

Ce dépôt contient le serveur pour l'application mobile, qui sert de backend pour les applications Android et iOS. Il est écrit en Python et utilise la bibliothèque aiohttp ainsi qu'une base de données MySQL.

## Fonctionnalités

- Utilisation des WebSockets pour envoyer des événements en temps réel aux utilisateurs de l'application mobile.
- Gestion des réponses de rappel de la passerelle de paiement.
- Gestion des notifications Firebase.
- Backend pour la génération de codes OTP (One Time Password).

## Installation

Pour installer ce projet localement, suivez ces étapes :

1. Clonez le dépôt :
   ```bash
   git clone https://github.com/EVPlug-ma/evplug-mobile-server.git
2. Accédez au répertoire du projet :
   cd evplug-mobile-server
3. Créez un environnement virtuel et activez-le :
   python -m venv env
   source env/bin/activate  # Sur Windows, utilisez `env\Scripts\activate`
4. Installez les dépendances nécessaires :
   pip install -r requirements.txt
5. Créez un fichier .env dans le répertoire du projet et ajoutez les configurations nécessaires :
6. Pour démarrer le serveur, exécutez la commande suivante :
   python server.py


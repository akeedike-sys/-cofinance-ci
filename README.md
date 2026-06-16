# COFINANCE CI - Plateforme Microfinance & Assurance Mobile

Plateforme numérique de gestion de microcrédits, d’assurance mobile et de support client en temps réel.
Développée avec Python 3.11+, Django 5.x et Django REST Framework.

## Fonctionnalités

1. **Authentification & Profils** : Gestion sécurisée avec JWT (`djangorestframework-simplejwt`) et rôles (Client, Agent, Admin).
2. **Gestion des Microcrédits** : Workflow de crédit (`Soumise` -> `En analyse` -> `Approuvée` -> `Décaissée`), score d'éligibilité automatique, génération automatique de l'échéancier.
3. **Suivi des Remboursements** : Enregistrement des paiements (partiels ou complets), pénalités de retard à 2% par jour, historique client.
4. **Assurance Mobile** : Catalogue d'offres et souscriptions avec gestion de date de validité.
5. **Tableau de Bord Administrateur** : KPIs opérationnels (taux de recouvrement, volume de crédits par statut, assurances actives) filtrables par date, agent et région.
6. **Notifications Internes** : Système d'alertes in-app sur changement d'état.
7. **Support Chat Temps Réel** : Chat bidirectionnel Client-Agent sous WebSockets (`Django Channels` + `Daphne`), avec indicateur de présence et de frappe ("en train d'écrire...").

---

## Installation et Lancement

### 1. Cloner le projet et installer les dépendances
```bash
# Installer les dépendances
pip install -r requirements.txt
```
### 2. Créer l'environnement virtuel


```bash
python -m venv venv


# Windows
venv\Scripts\activate


# macOS / Linux
source venv/bin/activate
```

### 2. Appliquer les migrations et initialiser la base de données
```bash
# Appliquer les migrations
python manage.py migrate

# Peupler la base avec les données de démonstration
python manage.py seed_db
```

### 3. Lancer le serveur ASGI (Daphne)
Pour que les WebSockets (le chat en temps réel) fonctionnent, vous **devez** lancer le serveur sous **Daphne** au lieu du serveur de développement classique Django.
```bash
daphne -b 127.0.0.1 -p 8000 cofinance_project.asgi:application
```

Accédez à l'application dans votre navigateur sur : [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

---

## Comptes de Démonstration (Seed DB)

Tous les comptes ont été pré-configurés avec des mots de passe connus pour faciliter les tests :

| Rôle | Nom d'utilisateur / Email | Mot de passe | Détails / Région |
| :--- | :--- | :--- | :--- |
| **Administrateur** | `admin` / `admin@cofinance.ci` | `admin123` | Accès global + Approbations |
| **Agent terrain 1** | `agent1` / `agent1@cofinance.ci` | `agent123` | Région Abidjan |
| **Agent terrain 2** | `agent2` / `agent2@cofinance.ci` | `agent123` | Région Bouaké |
| **Client 1** | `client1` / `client1@cofinance.ci` | `client123` | Abidjan (Revenu: 450k, crédit décaissé) |
| **Client 2** | `client2` / `client2@cofinance.ci` | `client123` | Korhogo (Revenu: 120k, crédit soumis) |

---

## Tâches planifiées (Alertes et Pénalités)

Pour lancer le traitement quotidien des relances d'échéances et des pénalités de retard, exécutez la commande personnalisée :
```bash
python manage.py check_reminders
```
Cette commande effectue :
- Rappels d'échéances à **J-3** (envoi d'une notification).
- Détection des retards de paiement (**J+1** et après), transition du statut en retard, application de la pénalité de 2% par jour et alerte client.
- Rappel d'expiration des polices d'assurance à **J-15** (envoi d'une notification).

---

## Documentation API

La documentation Swagger UI de l'API REST est accessible en local sur :
- **Swagger UI** : [http://127.0.0.1:8000/api/docs/](http://127.0.0.1:8000/api/docs/)
- **Redoc** : [http://127.0.0.1:8000/api/redoc/](http://127.0.0.1:8000/api/redoc/)

### Interface d'administration Django
Prérequis
- Python 3.13+
- PostgreSQL 18+ (configuré dans `settings.py`)
- Virtualenv activé

### Installation et Démarrage

1. **Activer l'environnement virtuel**
```powershell
.\venv\Scripts\Activate.ps1
```

2. **Appliquer les migrations**
```powershell
python manage.py migrate
```

3. **Lancer le serveur de développement**
```powershell
python manage.py runserver
nom utilisateur: admin
 [PASSWORD]:admin12345

4. **Accéder à l'application**
- Interface web : http://127.0.0.1:8000
- Admin Django : http://127.0.0.1:8000/admin
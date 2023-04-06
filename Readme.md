# SP API INTERNAL BUSINESS TOOL
This tool was developed while I worked with a privately held organization that was a group of Amazon Sellers. The application started in 2018 and evolved over the years from using Amazon MWS to using Amazon SP-API. The repository only contains the more later evolved code.

The application can be integrated into other Amazon businesses to implement a logical solution that allows for communication to Amazon SP-API.



## Features

- Add Items to Amazon Inventory
- Create Shipment Plan (***deprecated***)
- Automated process of request report to get report result
- Get Orders and Refund Information stored in DB
- Item Fees information.
- Slack Notifications.


## Requirements & Installations
- [Python](https://www.python.org/downloads/)
- [Celery](https://docs.celeryq.dev/en/stable/getting-started/first-steps-with-celery.html#installing-celery)
- [Redis](https://redis.io/download/)
- [Postgres SQL](https://www.postgresql.org/download/)
- For Window users, I recommend installing [Ubuntu on WSL](https://ubuntu.com/wsl) to run local development



## Running the Server Locally
#### STEP 1: Prepare Virtual Environments and Packages
Create a virtual enviroment, activate it and install packages in requirements.txt
```
python3 -m venv env -m
source env/bin/activate
pip install -r requirements.txt
```

#### STEP 2: Add Environment Variables
A list of environment variables are found in the .env.example file in the root folder.

- **App Variables**: `SECRET_KEY` `DEBUG`
- **SP-API Variables**: `REFRESH_TOKEN` `LWA_APP_ID` `LWA_CLIENT_SECRET` `AWS_ACCESS_KEY` `AWS_SECRET_KEY` `ROLE_ARN`
- **Database Variables**: `DB_HOST` `DB_NAME` `DB_PASSWORD`, `DB_PORT` `DB_USER`
- **Slack Variables (Optional)**: `SLACK_BOT_TOKEN` `SLACK_SCRIPT_UPDATE_CHANNEL`

#### STEP 3: Run Development Servers
Django Development Server
```
> python manage.py runserver
```
Redis:
```
> redis-server
```
Celery:
```
> celery -A AmazonApp worker --loglevel=INFO 
```
Celery Beat:
```
> celery -A AmazonApp beat --loglevel=INFO -S django --pidfile /tmp/celerybeat.pid
```


## Demo

- Development Server
<img src="/demo/development-server.png" alt="development-server.png">

- Redis Server
<img src="/demo/redis.png" alt="redis.png">

- Celery Workers
<img src="/demo/celery-worker.png" alt="celery-worker.png">

- Celery Beat (Cron) <i mg src="/demo/celery-beat.png" alt="celery-beat.png">



## Acknowledgements

- [Python Amazon SP-API Library by SaleWeaver](https://github.com/saleweaver/python-amazon-sp-api)

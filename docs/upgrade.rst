### Nginx webserver, Gunicorn app server, Celery task queue
Assumes services have been daemonized using systemd

1. Backup the application files

    `cp -R TolaTables backup/TolaTables`

2. Backup the MySQL database

    `mysqldump --events --max_allowed_packet=32M <database_name> --user=<mysql_user> -p > tables_backup.sql`

3. Backup MongoDB database

    `mongodump --db <database_name> --out mongo_backup -u <mongo_user>`

4. Shut down Nginx

    `sudo systemctl stop nginx`

5. Pull code changes

    `git pull <repo> master`

6. Update the database with model changes

    `python manage.py migrate`

7. Restart celery

    If any changes are made to the celery tasks, the celery process needs to be restarted.

    `sudo systemctl restart celery`

8. Restart gunicorn

    `sudo systemctl restart gunicorn`

9. Restart Nginx

    `sudo systemctl restart nginx`
# Diabetes Expert System

## Database migrations
If the migrations folder is not initialized yet, run:
```bash
flask db init
```

Then generate and apply the schema:
```bash
flask db migrate -m "init schema"
flask db upgrade
```

const { MONGO_APP_USER, MONGO_APP_PASSWORD, MONGO_DB } = process.env;

db.getSiblingDB(MONGO_DB).createUser({
  user: MONGO_APP_USER,
  pwd: MONGO_APP_PASSWORD,
  roles: [{ role: 'readWrite', db: MONGO_DB }],
});

// script to create default database collections and indexes
// on container start up

db = new Mongo().getDB("default");

db.createCollection('user', { capped: false });
db.createCollection('submission', { capped: false });
db.submission.createIndex({ "dateCreated": -1 });
db.submission.createIndex({ "datePublished": -1 });
db.submission.createIndex({ "lastModified": -1 });
db.submission.createIndex({ "submissionId": 1, unique: 1 });
db.user.createIndex({ "userId": 1, unique: 1 });
db.submission.createIndex(
  {
    text_name: "text",
  }
)
db.submission.getIndexes()

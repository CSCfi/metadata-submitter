// script to create default database collections and indexes
// on container start up

db = new Mongo().getDB("default");

db.createCollection('user', { capped: false });
db.createCollection('folder', { capped: false });
db.folder.createIndex({ "dateCreated": -1 });
db.folder.createIndex({ "datePublished": -1 });
db.folder.createIndex({ "lastModified": -1 });
db.folder.createIndex({ "folderId": 1, unique: 1 });
db.user.createIndex({ "userId": 1, unique: 1 });
db.folder.createIndex(
  {
    text_name: "text",
  }
)
db.folder.getIndexes()

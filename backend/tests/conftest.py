import os

os.environ.setdefault(
    "MONGO_URI",
    "mongodb://jogo_app:troque-esta-senha@localhost:27017/jogo_da_velha?authSource=jogo_da_velha",
)
os.environ.setdefault("MONGO_DB", "jogo_da_velha")

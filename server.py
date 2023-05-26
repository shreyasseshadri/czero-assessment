import json
import os
from fastapi import FastAPI
from pydantic import BaseModel
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from bson import json_util
from bson.objectid import ObjectId
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

# Configure MongoDB connection
password = os.getenv('DB_PASSWORD')
mongodb_url = "mongodb+srv://shreyas:"+str(password) + \
    "@cluster0.pdoqcww.mongodb.net/?retryWrites=true&w=majority"
client = MongoClient(mongodb_url, server_api=ServerApi('1'))
database = client["czero"]
collection = database["inventory"]

class Item(BaseModel):
    name: str
    variant: str
    sku: str
    qty: int
    description: str
    price: float


#Insert items into the MongoDB collection
@app.post("/items")
async def create_item(item: Item):
    item_dict = item.dict()
    inserted_item = collection.insert_one(item_dict)
    return {"id": inserted_item.inserted_id.__str__()}

#Update item in the MongoDB collection
@app.put("/items/{item_id}")
async def update_item(item_id: str, item: Item):
    item_dict = item.dict()
    with client.start_session() as session:
        with session.start_transaction():
            result = collection.update_one(
                {"_id": ObjectId(item_id)}, {"$set": item_dict},session=session)
            if result.modified_count == 1:
                return {"success": True}
            else:
                return {"success": False, "error": "Item not found"}

#Add to inventory count
@app.put("/items/{item_id}/add")
async def add_inventory_count(item_id: str):
    response = change_inventory_count(item_id, 1)
    del response["item"]
    return response

#Subtract from inventory count
@app.put("/items/{item_id}/remove")
async def remove_inventory_count(item_id: str):
    response = change_inventory_count(item_id, -1)
    del response["item"]
    return response

#Remove item from inventory
@app.delete("/items/{item_id}")
async def delete_item(item_id: str):
    collection.delete_one({"_id": ObjectId(item_id)})
    return {"id": item_id}

#Buys a list of items
@app.post("/buy")
async def buy_items(items: list):
    total_price = 0
    for product_item in items:
        id = product_item["id"]
        qty = product_item["qty"]
        response = change_inventory_count(id, -qty)
        if not response["success"]:
            return response
        ret_item = response["item"]
        total_price += ret_item["price"] * qty
    return {"success": True, "total_price": total_price}

# Change inventory with count
def change_inventory_count(item_id: str, delta: int):
    # Using a session to ensure that the transaction is atomic
    with client.start_session() as session:
        with session.start_transaction():
            item = collection.find_one(
                {"_id": ObjectId(item_id)}, session=session)
            if item:
                if item["qty"] + delta < 0:
                    return {"success": False, "error": "Not enough inventory." + " Only " + str(item["qty"]) + " items left for " + item["name"]}
                new_qty = item["qty"] + delta
                collection.update_one(
                    {"_id": ObjectId(item_id)},
                    {"$set": {"qty": new_qty}},
                    session=session
                )
                return {"success": True, "item": item}
            else:
                return {"success": False}


#Endpoint that searches a term across all fields
@app.get("/search")
async def search(term: str):
    results = list(collection.find(
        {"$text": {"$search": term}},
        {"score": {"$meta": "textScore"}}
    ).sort([("score", {"$meta": "textScore"})]))
    serialized_results = json_util.dumps(results)
    deserialized_results = json.loads(serialized_results)

    return deserialized_results

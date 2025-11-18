from db.base import db
from models.user import GreenApiInstance
from shared.user import get_user
from models.user import userContextDict
from store.user import UserStore
from firebase_admin import firestore
from green_api.instance_mng.create import pool_create_instance
POOL_SIZE = 1
import datetime

async def ensure_pool_ready():
    pool_ref = db.collection("instances_pool")

    docs = [doc for doc in pool_ref.limit(POOL_SIZE).stream()]
    ready_count = len(docs)

    if ready_count < POOL_SIZE:
        needed = POOL_SIZE - ready_count
        for _ in range(needed):
            idInstance, apiTokenInstance = pool_create_instance()
            idInstance = str(idInstance)
            pool_ref.document(idInstance).set({
                "idInstance": idInstance,
                "apiTokenInstance": apiTokenInstance,
                "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            })
        print(f"✨ Added {needed} new instance(s) to pool")

def claim_instance(user_id: str):
    transaction = db.transaction()

    @firestore.transactional
    def _claim(tx):
        pool_ref = db.collection("instances_pool")

        # get at most one doc inside this transaction
        docs = list(pool_ref.limit(1).get(transaction=tx))
        if not docs:
            raise RuntimeError("No ready instance available")

        doc = docs[0]
        inst = doc.to_dict()

        # remove from pool
        tx.delete(doc.reference)

        # attach to user.runtime
        user = get_user(user_id)
        user.runtime.greenApiInstance = GreenApiInstance(
            token=inst["apiTokenInstance"],
            id=inst["idInstance"],
        )
        UserStore(user_id).save(user)
        userContextDict[user_id] = user
        return inst

    return _claim(transaction)

def release_instance(user_id: str, inst: dict):
    """
    Return a claimed instance back to the pool and detach it from the user.
    inst should contain at least {"idInstance": str, "apiTokenInstance": str}
    """
    transaction = db.transaction()

    @firestore.transactional
    def _release(tx):
        pool_ref = db.collection("instances_pool")

        # put instance back in pool
        pool_ref.document(inst["idInstance"]).set(inst, transaction=tx)

        # detach from user
        user = get_user(user_id)
        if user and getattr(user, "runtime", None):
            user.runtime.greenApiInstance = None
            UserStore(user_id).save(user)
            userContextDict[user_id] = user

    return _release(transaction)

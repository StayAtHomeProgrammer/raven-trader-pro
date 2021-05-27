from jsonrpcclient.requests import Request
from requests import post, get
from decimal import *

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5 import uic

import sys, getopt, argparse, json, time, getpass, os.path
from util import *
from config import *
import urllib3
import traceback

def do_rpc(method, log_error=True, **kwargs):
    req = Request(method, **kwargs)
    try:
        resp = post(RPC_URL, json=req)
        if resp.status_code != 200:
            print("==>", req, "<== ERR: ")
            print(resp.text)
        return json.loads(resp.text)["result"]
    except Exception as error:
        raise RPCError("Could not connect to wallet RPC", error)



def decode_full(txid):
    resp = get(TX_QRY.format(txid))
    if resp.status_code != 200:
        print("Error fetching raw transaction")
    result = json.loads(resp.text)
    return result


def check_unlock(timeout=10):
    print("Unlocking Wallet for {}s".format(timeout))
    phrase_test = do_rpc("help", command="walletpassphrase")
    # returns None if no password set
    if (phrase_test.startswith("walletpassphrase")):
        do_rpc("walletpassphrase", passphrase=RPC_UNLOCK_PHRASE, timeout=timeout)


def dup_transaction(tx):
    new_vin = []
    new_vout = {}
    for old_vin in tx["vin"]:
        new_vin.append({"txid": old_vin["txid"], "vout": old_vin["vout"], "sequence": old_vin["sequence"]})
    for old_vout in sorted(tx["vout"], key=lambda vo: vo["n"]):  # What??
        vout_script = old_vout["scriptPubKey"]
        vout_addr = vout_script["addresses"][0]
        if (vout_script["type"] == "transfer_asset"):
            new_vout[vout_addr] = make_transfer(vout_script["asset"]["name"], vout_script["asset"]["amount"])
        else:
            new_vout[vout_addr] = old_vout["value"]
    return new_vin, new_vout


def search_swap_tx(utxo):
    utxo_parts = utxo.split("|")
    height = do_rpc("getblockcount")
    check_height = height
    while check_height >= height - 10:
        hash = do_rpc("getblockhash", height=check_height)
        details = do_rpc("getblock", blockhash=hash, verbosity=2)
        for block_tx in details["tx"]:
            for tx_vin in block_tx["vin"]:
                if "vout" in tx_vin and block_tx["txid"] == utxo_parts[0] and tx_vin["vout"] == int(utxo_parts[1]):
                    return block_tx["txid"]
        check_height -= 1
    print("Unable to find transaction for completed swap")
    return None  # If we don't find it 10 blocks back, who KNOWS what happened to it


class RPCError(Exception):
    def __init__(self, reason, baseException=None):
        self.reason = reason
        self.baseException = baseException  # The exception the caused us to raise the exception
        # Ex. urllib3.exceptions.HttpError --> RPCError

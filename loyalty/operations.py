from typing import Tuple, List

from algosdk.v2client.algod import AlgodClient
from algosdk.future import transaction
from algosdk.logic import get_application_address
from algosdk import account, encoding

from pyteal import compileTeal, Mode

from .account import Account
from .contracts import approval_program, clear_state_program
from .util import (
    waitForTransaction,
    fullyCompileContract,
    getAppGlobalState,
)

APPROVAL_PROGRAM = b""
CLEAR_STATE_PROGRAM = b""


def getContracts(client: AlgodClient) -> Tuple[bytes, bytes]:
    """Get the compiled TEAL contracts for the auction.
    Args:
        client: An algod client that has the ability to compile TEAL programs.
    Returns:
        A tuple of 2 byte strings. The first is the approval program, and the
        second is the clear state program.
    """
    global APPROVAL_PROGRAM
    global CLEAR_STATE_PROGRAM

    if len(APPROVAL_PROGRAM) == 0:
        APPROVAL_PROGRAM = fullyCompileContract(client, approval_program())
        CLEAR_STATE_PROGRAM = fullyCompileContract(client, clear_state_program())

    return APPROVAL_PROGRAM, CLEAR_STATE_PROGRAM


def createLoyaltyOfferApp(
    client: AlgodClient,
    sender: Account,
    customer: str,
    startTime: int,
    endTime: int,
    rewardAssetID: int,
    rewardAmount: int,
    actionID: int,
) -> int:
    """Create a new loyalty offer.
    Args:
        client: An algod client.
        sender: The account that will create the loyalty offer application.
        customer: The Account of the loyalty customer.
        startTime: A UNIX timestamp representing the start time of the offer.
            This must be greater than the current UNIX timestamp.
        endTime: A UNIX timestamp representing the end time of the offer. This
            must be greater than startTime.
        rewardAmount: The amount of the reward token that will be transferred to
            the loyalty customer after completion of the offer action(s).
        actionID: Identifier of action that must be performed to
            fulfill the offer requirement(s).
    Returns:
        The ID of the newly created auction app.
    """
    approval, clear = getContracts(client)

    globalSchema = transaction.StateSchema(num_uints=7, num_byte_slices=2)
    localSchema = transaction.StateSchema(num_uints=0, num_byte_slices=0)

    app_args = [
        encoding.decode_address(customer),
        startTime.to_bytes(8, "big"),
        endTime.to_bytes(8, "big"),
        rewardAssetID.to_bytes(8, "big"),
        rewardAmount.to_bytes(8, "big"),
        actionID.to_bytes(8, "big"),
    ]

    txn = transaction.ApplicationCreateTxn(
        sender=sender.getAddress(),
        on_complete=transaction.OnComplete.NoOpOC,
        approval_program=approval,
        clear_program=clear,
        global_schema=globalSchema,
        local_schema=localSchema,
        app_args=app_args,
        sp=client.suggested_params(),
    )

    signedTxn = txn.sign(sender.getPrivateKey())

    client.send_transaction(signedTxn)

    response = waitForTransaction(client, signedTxn.get_txid())
    assert response.applicationIndex is not None and response.applicationIndex > 0
    return response.applicationIndex


def setupLoyaltyOfferApp(
    client: AlgodClient,
    appID: int,
    funder: Account,
    rewardAssetID: int,
    rewardAmount: int,
) -> None:
    """Finish setting up an offer.
    This operation funds the app offer escrow account, in one atomic
    transaction group. The offer must not have started yet.
    The escrow account requires a total of 0.203 Algos for funding. See the code
    below for a breakdown of this amount.
    Args:
        client: An algod client.
        appID: The app ID of the auction.
        funder: The account providing the funding for the escrow account.
        rewardAssetID: The Reward Asset ID.
        rewardAmount: The number of reward tokens that a customer will recieve
            upon completion of the offer action requirements.
    """
    appAddr = get_application_address(appID)

    suggestedParams = client.suggested_params()

    fundingAmount = (
        # min account balance
        100_000
        # additional min balance to opt into NFT
        + 100_000
        # 3 * min txn fee
        + 3 * 1_000
    )

    fundAppTxn = transaction.PaymentTxn(
        sender=funder.getAddress(),
        receiver=appAddr,
        amt=fundingAmount,
        sp=suggestedParams,
    )

    setupTxn = transaction.ApplicationCallTxn(
        sender=funder.getAddress(),
        index=appID,
        on_complete=transaction.OnComplete.NoOpOC,
        app_args=[b"setup"],
        foreign_assets=[rewardAssetID],
        sp=suggestedParams,
    )

    fundAssetTxn = transaction.AssetTransferTxn(
        sender=funder.getAddress(),
        receiver=appAddr,
        index=rewardAssetID,
        amt=rewardAmount,
        sp=suggestedParams,
    )

    transaction.assign_group_id([fundAppTxn, setupTxn, fundAssetTxn])

    signedFundAppTxn = fundAppTxn.sign(funder.getPrivateKey())
    signedSetupTxn = setupTxn.sign(funder.getPrivateKey())
    signedFundAssetTxn = fundAssetTxn.sign(funder.getPrivateKey())

    client.send_transactions([signedFundAppTxn, signedSetupTxn, signedFundAssetTxn])

    waitForTransaction(client, signedFundAppTxn.get_txid())


def completeAction(client: AlgodClient, owner: Account, appID: int, actionID: int) -> None:
    """Complete an offer action requirement.
    Args:
        client: An Algod client.
        owner: The offer contract creator.
        appID: The app ID of the auction.
        actionID: The identifier of action that was performed.
    """
    appGlobalState = getAppGlobalState(client, appID)

    rewardTokenID = appGlobalState[b"reward_asset_id"]

    if any(appGlobalState[b"customer_account"]):
        # if "bid_account" is not the zero address
        customerAccount = encoding.encode_address(appGlobalState[b"customer_account"])
    else:
        customerAccount = None

    suggestedParams = client.suggested_params()

    appCallTxn = transaction.ApplicationCallTxn(
        sender=owner.getAddress(),
        index=appID,
        on_complete=transaction.OnComplete.NoOpOC,
        app_args=["action", actionID],
        foreign_assets=[rewardTokenID],
        accounts=[customerAccount] if customerAccount is not None else [],
        sp=suggestedParams,
    )

    transaction.assign_group_id([appCallTxn])

    signedAppCallTxn = appCallTxn.sign(owner.getPrivateKey())

    client.send_transactions([signedAppCallTxn])

    waitForTransaction(client, appCallTxn.get_txid())


def closeLoyaltyOffer(client: AlgodClient, appID: int, closer: Account):
    """Close a loyalty offer.
    This action can only happen before an offer has begun, in which case it is
    cancelled, or after an offer has expired.
    If called after the offer has expired and the offer actions were not completed, the
    offer reward is transferred back to the offer contract creator, since if the actions
    were completed the offer reward should have been transferred to the customer.
    Args:
        client: An Algod client.
        appID: The app ID of the auction.
        closer: The account initiating the close transaction. This must be
            the offer creator if you wish to close the
            offer before it starts. Otherwise, this can be any account.
    """
    appGlobalState = getAppGlobalState(client, appID)

    rewardAssetID = appGlobalState[b"reward_asset_id"]

    accounts: List[str] = [encoding.encode_address(appGlobalState[b"customer_account"])]

    deleteTxn = transaction.ApplicationDeleteTxn(
        sender=closer.getAddress(),
        index=appID,
        accounts=accounts,
        foreign_assets=[rewardAssetID],
        sp=client.suggested_params(),
    )
    signedDeleteTxn = deleteTxn.sign(closer.getPrivateKey())

    client.send_transaction(signedDeleteTxn)

    waitForTransaction(client, signedDeleteTxn.get_txid())
from time import time, sleep

from algosdk import account, encoding
from algosdk.logic import get_application_address
from loyalty.operations import createLoyaltyOfferApp, setupLoyaltyOfferApp, completeAction, closeLoyaltyOffer
from loyalty.util import (
    getBalances,
    getAppGlobalState,
    getLastBlockTimestamp,
)
from loyalty.testing.setup import getAlgodClient
from loyalty.testing.resources import (
    getTemporaryAccount,
    optInToAsset,
    createDummyAsset,
)


def simple_loyalty_offer():
    client = getAlgodClient()

    print("Generating temporary accounts...")
    creator = getTemporaryAccount(client)
    customer1 = getTemporaryAccount(client)

    print("Bob (offer(s) creator account):", creator.getAddress())
    print("Alice (customer1 account):", customer1.getAddress())

    print("Bob is generating an loyalty program asset...")
    rewardAssetAmount = 1_000_000
    rewardAssetID = createDummyAsset(client, rewardAssetAmount, creator)
    print("The reward asset ID is", rewardAssetID)
    print("Bob's balances:", getBalances(client, creator.getAddress()), "\n")

    startTime = int(time()) + 10  # start time is 10 seconds in the future
    endTime = startTime + 30  # end time is 60 seconds after start
    offer1Reward = 100  # 100 "points"
    print("Bob is creating an offer for Alice which lasts 60 seconds to join a discord channel to receive 100 "
          "\"points\"")
    offer1ID = createLoyaltyOfferApp(
        client=client,
        sender=creator,
        customer=customer1.getAddress(),
        startTime=startTime,
        endTime=endTime,
        rewardAssetID=rewardAssetID,
        rewardAmount=offer1Reward,
        actionID=1010, # let's pretend that this is join a discord channel
    )
    print(
        "Done. The offer app ID is",
        offer1ID,
        "and the escrow account is",
        get_application_address(offer1ID),
        "\n",
    )

    print("Bob is setting up and funding loyalty offers...")
    setupLoyaltyOfferApp(
        client=client,
        appID=offer1ID,
        funder=creator,
        rewardAssetID=rewardAssetID,
        rewardAmount=offer1Reward,
    )
    print("Done\n")

    customerBalancesBefore = getBalances(client, customer1.getAddress())
    print("Alice's balances before offer:", customerBalancesBefore)

    _, lastRoundTime = getLastBlockTimestamp(client)
    if lastRoundTime < startTime + 5:
        sleep(startTime + 5 - lastRoundTime)
    actualAppBalancesBefore = getBalances(client, get_application_address(offer1ID))
    print("Offer escrow balances:", actualAppBalancesBefore, "\n")

    print("Alice is opting into Reward asset with ID", rewardAssetID)

    optInToAsset(client, rewardAssetID, customer1)

    print("Alice is completing the offer action (joining Discord channel)...")

    completeAction(client=client, owner=creator, appID=offer1ID, actionID=1010)

    print("Done\n")

    _, lastRoundTime = getLastBlockTimestamp(client)
    if lastRoundTime < endTime + 5:
        waitTime = endTime + 5 - lastRoundTime
        print("Waiting {} seconds for the offer to expire\n".format(waitTime))
        sleep(waitTime)

    print("Bob is closing out the offer\n")
    closeLoyaltyOffer(client, offer1ID, creator)

    actualAppBalances = getBalances(client, get_application_address(offer1ID))
    expectedAppBalances = {0: 0}
    print("The offer escrow now holds the following:", actualAppBalances)
    assert actualAppBalances == expectedAppBalances

    customerPointsBalance = getBalances(client, customer1.getAddress())[rewardAssetID]
    print("Alice's reward balance after completing the offer: {}", customerPointsBalance)
    assert customerPointsBalance == offer1Reward

    creatorRewardBalance = getBalances(client, creator.getAddress())[rewardAssetID]
    print("Bob's reward balance after sending reward to Alice: {}", creatorRewardBalance)
    assert creatorRewardBalance == rewardAssetAmount - offer1Reward


simple_loyalty_offer()

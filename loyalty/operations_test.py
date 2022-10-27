from time import time, sleep

import pytest

from algosdk import account, encoding
from algosdk.logic import get_application_address

from .operations import createLoyaltyOfferApp, setupLoyaltyOfferApp, completeAction, closeLoyaltyOffer
from .util import getBalances, getAppGlobalState, getLastBlockTimestamp
from .testing.setup import getAlgodClient
from .testing.resources import getTemporaryAccount, optInToAsset, createDummyAsset


def test_create():
    client = getAlgodClient()

    creator = getTemporaryAccount(client)
    _, customer_addr = account.generate_account()  # random address

    tokenAmount = 1_000
    tokenID = createDummyAsset(client, tokenAmount, creator)

    startTime = int(time()) + 10  # start time is 10 seconds in the future
    endTime = startTime + 60  # end time is 1 minute after start
    rewardAmount = 100  # 100 reward tokens
    actionID = 101

    appID = createLoyaltyOfferApp(
        client=client,
        sender=creator,
        customer=customer_addr,
        startTime=startTime,
        endTime=endTime,
        rewardAssetID=tokenID,
        rewardAmount=rewardAmount,
        actionID=actionID,
    )

    actual = getAppGlobalState(client, appID)
    expected = {
        b"customer_account": encoding.decode_address(customer_addr),
        b"start": startTime,
        b"end": endTime,
        b"reward_asset_id": tokenID,
        b"reward_amount": rewardAmount,
        b"action_id": actionID,
        b"status": 1,
    }

    assert actual == expected


def test_setup():
    client = getAlgodClient()

    creator = getTemporaryAccount(client)
    customer = getTemporaryAccount(client)

    tokenAmount = 1_000
    tokenID = createDummyAsset(client, tokenAmount, creator)

    startTime = int(time()) + 10  # start time is 10 seconds in the future
    endTime = startTime + 60  # end time is 1 minute after start
    rewardAmount = 100  # 100 reward tokens (e.g. points, miles, starts etc.)
    actionID = 101

    appID = createLoyaltyOfferApp(
        client=client,
        sender=creator,
        customer=customer.getAddress(),
        startTime=startTime,
        endTime=endTime,
        rewardAssetID=tokenID,
        rewardAmount=rewardAmount,
        actionID=actionID,
    )

    setupLoyaltyOfferApp(
        client=client,
        appID=appID,
        funder=creator,
        rewardAssetID=tokenID,
        rewardAmount=rewardAmount
    )

    actualState = getAppGlobalState(client, appID)
    expectedState = {
        b"customer_account": encoding.decode_address(customer.getAddress()),
        b"start": startTime,
        b"end": endTime,
        b"reward_amount": rewardAmount,
        b"reward_asset_id": tokenID,
        b"action_id": actionID,
        b"status": 2,
    }

    assert actualState == expectedState

    actualBalances = getBalances(client, get_application_address(appID))
    expectedBalances = {0: 2 * 100_000 + 2 * 1_000, tokenID: rewardAmount}

    assert actualBalances == expectedBalances


def test_complete_action_before_start():
    client = getAlgodClient()

    creator = getTemporaryAccount(client)
    customer = getTemporaryAccount(client)

    tokenAmount = 1_000
    tokenID = createDummyAsset(client, tokenAmount, creator)

    startTime = int(time()) + 5 * 60  # start time is 5 minutes in the future
    endTime = startTime + 60  # end time is 1 minute after start
    rewardAmount = 100  # 100 reward tokens
    actionID = 101

    appID = createLoyaltyOfferApp(
        client=client,
        sender=creator,
        customer=customer.getAddress(),
        startTime=startTime,
        endTime=endTime,
        rewardAssetID=tokenID,
        rewardAmount=rewardAmount,
        actionID=actionID,
    )

    setupLoyaltyOfferApp(
        client=client,
        appID=appID,
        funder=creator,
        rewardAssetID=tokenID,
        rewardAmount=rewardAmount
    )

    _, lastRoundTime = getLastBlockTimestamp(client)
    assert lastRoundTime < startTime

    with pytest.raises(Exception):
        completeAction(client=client, owner=creator, appID=appID, actionID=actionID)


def test_complete_action():
    client = getAlgodClient()

    creator = getTemporaryAccount(client)
    customer = getTemporaryAccount(client)

    tokenAmount = 1_000
    tokenID = createDummyAsset(client, tokenAmount, creator)

    startTime = int(time()) + 10  # start time is 10 seconds in the future
    endTime = startTime + 300  # end time is 5 minutes after start
    rewardAmount = 100  # 1 reward tokens
    actionID = 101

    appID = createLoyaltyOfferApp(
        client=client,
        sender=creator,
        customer=customer.getAddress(),
        startTime=startTime,
        endTime=endTime,
        rewardAssetID=tokenID,
        rewardAmount=rewardAmount,
        actionID=actionID,
    )

    setupLoyaltyOfferApp(
        client=client,
        appID=appID,
        funder=creator,
        rewardAssetID=tokenID,
        rewardAmount=rewardAmount,
    )

    appContractBalances = getBalances(client, get_application_address(appID))
    assert appContractBalances == {0: 2 * 100_000 + 2 * 1000, tokenID: rewardAmount}

    _, lastRoundTime = getLastBlockTimestamp(client)
    if lastRoundTime < startTime + 5:
        sleep_time = startTime + 5 - lastRoundTime
        sleep(sleep_time)

    completeAction(client=client, owner=creator, appID=appID, actionID=actionID)

    actualState = getAppGlobalState(client, appID)
    expectedState = {
        b"customer_account": encoding.decode_address(customer.getAddress()),
        b"start": startTime,
        b"end": endTime,
        b"reward_asset_id": tokenID,
        b"reward_amount": rewardAmount,
        b"action_id": actionID,
        b"status": 3,
    }

    assert actualState == expectedState

    actualAppBalances = getBalances(client, get_application_address(appID))
    expectedAppBalances = {0: 2 * 100_000 + 1 * 1000, tokenID: 0}

    assert actualAppBalances == expectedAppBalances

    customerAlgoBalance = getBalances(client, customer.getAddress())[tokenID]

    assert customerAlgoBalance == rewardAmount


def test_close_before_start():
    client = getAlgodClient()

    creator = getTemporaryAccount(client)
    customer = getTemporaryAccount(client)

    startTime = int(time()) + 5 * 60  # start time is 5 minutes in the future
    endTime = startTime + 60  # end time is 1 minute after start
    rewardAmount = 1_000_000  # 1 Algo
    actionID = 101

    appID = createLoyaltyOfferApp(
        client=client,
        sender=creator,
        customer=customer.getAddress(),
        startTime=startTime,
        endTime=endTime,
        rewardAmount=rewardAmount,
        actionID=actionID,
    )

    setupLoyaltyOfferApp(
        client=client,
        appID=appID,
        funder=creator,
    )

    _, lastRoundTime = getLastBlockTimestamp(client)
    assert lastRoundTime < startTime

    closeLoyaltyOffer(client, appID, creator)

    actualAppBalances = getBalances(client, get_application_address(appID))
    expectedAppBalances = {0: 0}

    assert actualAppBalances == expectedAppBalances


def test_close_no_action():
    client = getAlgodClient()

    creator = getTemporaryAccount(client)
    customer = getTemporaryAccount(client)

    startTime = int(time()) + 10  # start time is 10 seconds in the future
    endTime = startTime + 30  # end time is 30 seconds after start
    rewardAmount = 1_000_000  # 1 Algo
    actionID = 101

    appID = createLoyaltyOfferApp(
        client=client,
        sender=creator,
        customer=customer.getAddress(),
        startTime=startTime,
        endTime=endTime,
        rewardAmount=rewardAmount,
        actionID=actionID,
    )

    setupLoyaltyOfferApp(
        client=client,
        appID=appID,
        funder=creator,
    )

    _, lastRoundTime = getLastBlockTimestamp(client)
    if lastRoundTime < endTime + 5:
        sleep(endTime + 5 - lastRoundTime)

    closeLoyaltyOffer(client, appID, creator)

    actualAppBalances = getBalances(client, get_application_address(appID))
    expectedAppBalances = {0: 0}

    assert actualAppBalances == expectedAppBalances

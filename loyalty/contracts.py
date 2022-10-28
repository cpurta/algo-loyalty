from pyteal import *


def approval_program():
    customer_account_key = Bytes("customer_account")
    start_time_key = Bytes("start")
    end_time_key = Bytes("end")
    reward_asset_id_key = Bytes("reward_asset_id")
    reward_amount_key = Bytes("reward_amount")
    action_id_key = Bytes("action_id")
    status_key = Bytes("status")

    # This should close the reward amount to the customer
    @Subroutine(TealType.none)
    def closeRewardTo(assetID: Expr, account: Expr) -> Expr:
        return Seq(
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.AssetTransfer,
                    TxnField.xfer_asset: assetID,
                    TxnField.asset_close_to: account,
                }
            ),
            InnerTxnBuilder.Submit(),
        )

    @Subroutine(TealType.none)
    def closeAccountTo(account: Expr) -> Expr:
        return If(Balance(Global.current_application_address()) != Int(0)).Then(
            Seq(
                InnerTxnBuilder.Begin(),
                InnerTxnBuilder.SetFields(
                    {
                        TxnField.type_enum: TxnType.Payment,
                        TxnField.close_remainder_to: account,
                    }
                ),
                InnerTxnBuilder.Submit(),
            )
        )

    on_create_start_time = Btoi(Txn.application_args[1])
    on_create_end_time = Btoi(Txn.application_args[2])
    on_create_reward_asset_id = Btoi(Txn.application_args[3])
    on_create_reward_amount = Btoi(Txn.application_args[4])
    on_create_action_id = Btoi(Txn.application_args[5])
    on_create = Seq(
        App.globalPut(customer_account_key, Txn.application_args[0]),
        App.globalPut(start_time_key, on_create_start_time),
        App.globalPut(end_time_key, on_create_end_time),
        App.globalPut(reward_asset_id_key, on_create_reward_asset_id),
        App.globalPut(reward_amount_key, on_create_reward_amount),
        App.globalPut(action_id_key, on_create_action_id),
        # set the offer status to 1 as an enumeration for 'created'
        App.globalPut(status_key, Int(1)),
        Assert(
            And(
                Global.latest_timestamp() < on_create_start_time,
                on_create_start_time < on_create_end_time,
            )
        ),
        Approve(),
    )

    on_setup = Seq(
        Assert(Global.latest_timestamp() < App.globalGet(start_time_key)),
        # opt into NFT asset -- because you can't opt in if you're already opted in, this is what
        # we'll use to make sure the contract has been set up
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields(
            {
                TxnField.type_enum: TxnType.AssetTransfer,
                TxnField.xfer_asset: App.globalGet(reward_asset_id_key),
                TxnField.asset_receiver: Global.current_application_address(),
            }
        ),
        InnerTxnBuilder.Submit(),
        App.globalPut(status_key, Int(2)),
        Approve(),
    )

    action_id_bytes = Txn.application_args[1]
    action_id_identical = Btoi(action_id_bytes) == App.globalGet(action_id_key)
    on_action = Seq(
        Assert(
            And(
                # the offer has started
                App.globalGet(start_time_key) <= Global.latest_timestamp(),
                # the offer has not ended
                Global.latest_timestamp() < App.globalGet(end_time_key),
                # the offer has not already been completed
                App.globalGet(status_key) != Int(3),
                Txn.type_enum() == TxnType.ApplicationCall,
            )
        ),
        If(
            action_id_identical
        ).Then(
            Seq(
                App.globalPut(status_key, Int(3)),
                # pay out the offer reward to the customer address
                closeRewardTo(App.globalGet(reward_asset_id_key), App.globalGet(customer_account_key)),
                Approve(),
            )
        ),
        Approve()
    )

    on_call_method = Txn.application_args[0]
    on_call = Cond(
        [on_call_method == Bytes("setup"), on_setup],
        [on_call_method == Bytes("action"), on_action],
    )

    on_delete = Seq(
        If(Global.latest_timestamp() < App.globalGet(start_time_key)).Then(
            Seq(
                # the offer has not yet started, it's ok to delete
                Assert(
                    # sender must be the offer creator
                    Txn.sender() == Global.creator_address(),
                ),
                # if the offer contract still has funds, send them all to the offer creator
                closeRewardTo(App.globalGet(reward_asset_id_key), Global.creator_address()),
                closeAccountTo(Global.creator_address()),
                Approve(),
            )
        ),
        If(App.globalGet(end_time_key) <= Global.latest_timestamp()).Then(
            Seq(
                # the offer was not completed because the customer did not complete the action
                # return the rewards back to the offer creator to be reclaimed
                If(App.globalGet(status_key) != Int(3)).Then(
                    closeRewardTo(App.globalGet(reward_asset_id_key), Global.creator_address())
                ),
                # send remaining funds to the seller
                closeAccountTo(Global.creator_address()),
                Approve(),
            )
        ),
        Reject(),
    )

    program = Cond(
        [Txn.application_id() == Int(0), on_create],
        [Txn.on_completion() == OnComplete.NoOp, on_call],
        [
            Txn.on_completion() == OnComplete.DeleteApplication,
            on_delete,
        ],
        [
            Or(
                Txn.on_completion() == OnComplete.OptIn,
                Txn.on_completion() == OnComplete.CloseOut,
                Txn.on_completion() == OnComplete.UpdateApplication,
            ),
            Reject(),
        ],
        [Txn.application_args[0] == Bytes("action"), on_action],
    )

    return program


def clear_state_program():
    return Approve()


if __name__ == "__main__":
    with open("offer_approval.teal", "w") as f:
        compiled = compileTeal(approval_program(), mode=Mode.Application, version=5)
        f.write(compiled)

    with open("offer_clear_state.teal", "w") as f:
        compiled = compileTeal(clear_state_program(), mode=Mode.Application, version=5)
        f.write(compiled)

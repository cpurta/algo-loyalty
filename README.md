# algo-loyalty
A loyalty reward program built for the Algorand ecosystem. This allows an adminstrator
to create and assign a offer to a "customer" or member of the loyalty program.

## Design

The design of the loyalty program is mostly broken into the PyTeal smart contract. This
allows for more flexible development of how the offer contract actions can be fufilled.

![Algorand Loyalty](https://user-images.githubusercontent.com/7330964/199258212-8409df2e-2567-4ccd-afa8-c79e03718355.png)

## Example

Imagine that you want a loyalty memeber to sign-up for your loyalty program and once they
have done so you want them to join your Discord server and post an intro message. This would
be difficult for a smart contract to communicate with external resources (i.e. an custom sign-up and
discord oracle). So the smart contract has the concept of a "action_id" that is managed by
the contract creator. 

So in our example we could create and manage a couple of `action_id`'s:

```
sign_up_action_id = 101
join_discord_and_post = 102
```

We could then create a couple of offers for each action for a loyalty member. Once the offer
is created an "action manager" application can keep track of the action(s) a member needs to
accomplish. This could be connecting to 3rd party APIs or connecting to a Database. Once the
action manager determines that the correct action has been accomplished it can then call the
"completeAction" contract application call to complete the offer and pay out the reward to 
the loyalty member.

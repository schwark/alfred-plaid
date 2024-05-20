# Alfred  Workflow for Transaction Search via Plaid

## Install

* Download .workflow file from [Releases](https://github.com/schwark/alfred-plaid/releases)
* Can also be downloaded from github as a zip file, unzip the downloaded zip, cd into the zip directory, and create a new zip with all the files in that folder, and then renamed to Plaid.alfredworkflow
* Or you can use the workflow-build script in the folder, using
```
chmod +x workflow-build
./workflow-build . 
```
* You will need a client ID and secret from the Plaid API portal. Sign up for a free developer account at Plaid, and ask for access to the development environment. The keys to enter into this workflow are the client ID and secret for the Development environment. It cannot be Sandbox environment credentials. This is free to sign up and use forever (according to Plaid)

**NOTE**: All these options mentioned below should show up with a dropdown option to autocomplete the option if you start typing some of what you are looking to do in english

## Client ID

```
pd clientid <client-id>
```
This should only be needed once per install or after a reinit

## Client Secret

```
pd secret <secret>
```
This should only be needed once per install or after a reinit

## Account Linking

```
pd link
```
This should be needed whenever you want to link a new account, or update the link/passwords to an existing account


## Account/Transactions Update

```
pd update
```
This should be needed once a day or as needed - this updates the local cache of all the transactions

## Category Update

```
pd upcat
```
This should be needed once a month or as needed - this updates the local cache of all the categories

## Account Details

```
pd act:
```
This gives the list of accounts and balances, and selecting any of them also filters all further queries to that account. Mulitple accounts can be filtered on, by selecting more than one consecutively. Selecting "All Accounts" will reset account filtering

## Account Refresh

```
pd refresh <all | item>
```
This allows for forcing a refresh of the data from the bank to Plaid. You can refresh all items as well. This only refreshes from the bank to plaid. To update the local cache of transactions, this needs to be followed by a `update` command a few mins later when the refresh may be complete.

## Account Filtering

```
pd filter act:<acct-name>
```
This allows for adding or removing accounts to a permanent account filter that applies to all further queries till it is set or removed again.

## Account Nicknaming

```
pd nick <nickname> act:<acct-name>
```
This allows for adding a nickname to any given account

## Environment Selection

```
pd env
```
The environment should be set to production, but using Sandbox will allow you to test this with dummy accounts.

## Basic Transaction Search queries

```
pd <act:acct-name?> <dt:(this|last)-(week|month|quarter|half|year)?> <dtf:from-date?> <dtt:to-date?> <amtt:to-amount?> <amtf:from-amount?> <cht:?>
<ct:p(ie)|(d)oughnut|b(ar)|l(ine)?> <ta:d(ay)|w(eek)|m(onth)?> <ma:m(erchant)|c(ategory)?> <cat:cat-id?> <search-term> 
```
The search term is the only required entry, further filtering is possible by using modifiers. All those additional fiters are optional. If any of the other modifiers are specified, the search term is also optional

```
act:<acct>              filter transactions to only this account for this query only
dtf:<from-date>         transactions on or after this date
dtt:<to-date>           transactions on or before this date
amtt:<to-amount>        transactions with amounts less than or equal to this amount
amtf:<from-amount>      transactions with amounts greater than or equal to this amount
dt:<last-month>         a shortcut way of specifying dtf and dtt for some commons scenarios
cat:<cat-id>            filter transactions by category - cat:<search-term> will show all available
cht:                    add a charting link to the results of transactions
ct:<p|d|b|l>            choose a chart type from pie, doughnut, bar or line
ta:<d|w|m>              choose periods to chart over from day, week or month
ma:<m|c>                choose a charting segment to total over from merchant or category for each transaction
```
NOTE: Category search with `cat:` will also include all the subcategories of the category chosen.

## Charting

Any transaction query as above that includes `cht:` in the query will show a link to a chart as the first result - hitting the `SHIFT` key (NO click - only tap `SHIFT` key) will popup the chart. The exact style of the chart can be customized using the `ct:`, `ta:`, and `ma:` modifiers to any transaction query.

## Transaction Category Customization

Any transaction can be customized to something else. When that is done that merchant is reclassified across all transactions to the new category. To do this, search for the transaction in question and then `ENTER` to select the transaction (ignore the long string that shows up) and then add `cht:` or type `c` and choose `Choose Category`. Type in a few letters to find the category you want. Choose the category to reclassify to. The result will update to the transaction, and the subtitle will update to `Change category to ...`. Hit `ENTER` to reclassify. Now all transactions with that merchant will now be reclassified to this new category

## Clear

```
pd clear
```
This clears all transaction data and merchant and category data. It retains the client id, secret and even the items already linked. But all account and transaction data is removed. NOTE: the environment being used is set back to default value as well with this operation. Use as needed.


## Reinitialize

```
pd reinit
```
This should only be needed if you ever want to start again for whatever reason - removes all client id, secret, and most importantly already linked items. Once the items are nuked, there is no way to get those linked items back. You will need to add new items to your Plaid account and it may have billing implications as there will be multiple items on Plaid side for the same bank on your side. Use with caution and only when REALLY necessary. `pd clear` is often the better option.

## Update

```
pd workflow:update
```
An update notification should show up when an update is available, but if not invoking this should update the workflow to latest version on github

## Acknowledgements

Icons made by [Freepik](https://www.flaticon.com/authors/freepik) and by [Roundicons Premium](https://www.freepik.com/author/roundicons/icons/generic-color-lineal-color_1640576)
Icons also from [IconFinder](https://www.iconfinder.com/)
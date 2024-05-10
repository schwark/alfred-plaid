# Alfred  Workflow for Transaction Search via Plaid

## Install

* Download .workflow file from [Releases](https://github.com/schwark/alfred-plaid/releases)
* Can also be downloaded from github as a zip file, unzip the downloaded zip, cd into the zip directory, and create a new zip with all the files in that folder, and then renamed to Smartthings.alfredworkflow
* Or you can use the workflow-build script in the folder, using
```
chmod +x workflow-build
./workflow-build . 
```
* You will need a client ID and secret from the Plaid API portal. Sign up for a free developer account at Plaid, and ask for access to the development environment. The keys to enter into this workflow are the client ID and secret for the Development environment. It cannot be Sandbox environment credentials. This is free to sign up and use forever (according to Plaid)

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

## Account/Transactions Update

```
pd update
```
This should be needed once a day or as needed - this updates the local cache of all the transactions

## Account Details and Filtering

```
pd act:
```
This gives the list of accounts and balances, and selecting any of them also filters all further queries to that account. Mulitple accounts can be filtered on, by selecting more than one consecutively. Selecting "All Accounts" will reset account fltering

## Environment Selection

```
pd env
```
The environment should be set to production, but using Sandbox will allow you to test this with dummy accounts.

## Basic Transaction queries

```
pd <dt:(this|last)-(week|month|quarter|year)?> <dtf:from-date?> <dtt:to-date?> <amtt:to-amount?> <amtf:from-amount?> <cp:p(ie)|b(ar)|l(ine)> <ta:d(ay)|w(eek)|m(onth)> <ma:m(erchant)|c(ategory)> <search-term> 
```
The search term is the only required entry, further filtering is possible by using modifiers. All those additional fiters are optional.

```
dtf:<from-date>         transactions on or after this date
dtt:<to-date>           transactions on or before this date
amtt:<to-amount>        transactions with amounts less than or equal to this amount
amtf:<from-amount>      transactions with amounts greater than or equal to this amount
dt:<last-month>         a shortcut way of specifying dtf and dtt for some commons scenarios
cp:<p|b|l>              choose a chart type from pie, bar or line
ta:<d|w|m>              choose periods to chart over from day, week or month
ma:<m|c>                choose a charting segment to total over from merchant or category for each transaction
```

## Reinitialize

```
pd reinit
```
This should only be needed if you ever want to start again for whatever reason - removes all API keys, devices, scenes, etc.

## Update

```
pd workflow:update
```
An update notification should show up when an update is available, but if not invoking this should update the workflow to latest version on github

## Acknowledgements

Icons made by [Freepik](https://www.flaticon.com/authors/freepik) from [www.flaticon.com](https://www.flaticon.com)  
Icons also from [IconFinder](https://www.iconfinder.com/)
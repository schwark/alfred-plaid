from workflow import web
import json
from common import ensure_icon, get_protocol, get_category_icon, qnotify

ERROR_MESSAGES = {
    'default': "Plaid API Error",
    'ITEM_LOGIN_REQUIRED': "Login needs updating"
}

class Plaid:
    def __init__(self, client_id, secret, user_id, environment='sandbox', logger=None, datadir=None):
        self.client_id = client_id
        self.secret = secret
        self.user_id = user_id
        self.environment = str(environment)
        self.logger = logger
        self.datadir = datadir
        
    def debug(self, text):
        if(self.logger): self.logger.debug(text)
        
    def api(self, path, data={}, no_auth=False):
        url = f'https://{self.environment}.plaid.com{path}'
        headers = {'Accept':"application/json", 'Content-Type': "application/json"}
        params = {'client_id': self.client_id, 'secret': self.secret} if not no_auth else {}
        params = {**params, **data}
        r = None
        self.debug("plaid_api: url:"+url+", headers: "+str(headers)+", params: "+str(params))
        r = web.post(url, headers=headers, data=json.dumps(params))
        self.debug("plaid_api: url:"+url+", headers: "+str(headers)+", params: "+str(params)+", return code: "+str(r.status_code))
        # throw an error if request failed
        # Workflow will catch this and show it to the user
        result = None
        if(r.status_code == 200):
            # Parse the JSON returned by pinboard and extract the posts
            result = r.json()
            #self.debug(str(result))
        else:
            result = r.json()
            if result and 400 == r.status_code and 'error_code' in result:
                error = ERROR_MESSAGES[result['error_code']] if result['error_code'] in ERROR_MESSAGES else ERROR_MESSAGES['default']
                qnotify('Plaid', error)
        return result   
    
    def get_categories(self, wf):
        categories = {}
        result = self.api(path="/categories/get", data={}, no_auth=True)
        if 'categories' in result:
            for category in result['categories']:
                id = int(category['category_id'])
                icon = get_category_icon(wf, category['hierarchy'])
                #wf.logger.debug(f"{category['hierarchy']}:  {icon}")
                categories[id] = {
                    'id': id,
                    'list': category['hierarchy'],
                    'icon': icon
                }
        return categories
    
    def get_link_token(self, item, proto='https'):
        update = item and 'access_token' in item
        if not update and item and item.get('link_token'):
            data = {'link_token': item.get('link_token')}
            result = self.api(path="/link/token/get", data=data)
            if 'link_token' in result:
                item['link_token'] = result['link_token']
                return result['link_token']
        data = {
            "client_name": "Alfred Plaid Search", 
            "country_codes": ["US"], 
            "language": "en", 
            "redirect_uri": f"{proto}://localhost:8383/oauth.html",
            "user": {"client_user_id": self.user_id}
        }
        products = {"products": ["transactions"]}
        access = {"access_token": item.get('access_token')}
        if(update and item.get('access_token')):
            data = {**data, **access}
        else:
            data = {**data, **products}
        result = self.api(path="/link/token/create", data=data)
        if 'link_token' in result:
            item['link_token'] = result['link_token']
            self.debug('link token is '+result['link_token'])
            return result['link_token']
        else:
            return None
        
    def get_institution_by_id(self, institution_id):
        data = {'institution_id': institution_id, 'country_codes': ['US'], 'options': {'include_optional_metadata': True}}
        result = self.api(path="/institutions/get_by_id", data=data)
        if result and 'institution' in result:
            result = result['institution']
        return result

    def exchange_public_token(self, public_token):
        data = {"public_token": public_token}
        result = self.api(path="/item/public_token/exchange", data=data)
        return result
    
    def get_item(self, access_token):
        data = {"access_token": access_token}
        result = self.api(path="/item/get", data=data)
        return result
    
    def get_accounts(self, item, banks):
        data = {"access_token": item.get('access_token')}
        result = self.api(path="/accounts/get", data=data)
        if 'error_code' in result:
            return result['error_code']
        
        bank = None
        if 'item' in result and 'institution_id' in result['item']:
            if result['item']['institution_id'] not in banks:
                bank = self.get_institution_by_id(result['item']['institution_id'])
                banks[result['item']['institution_id']] = bank
            else:
                bank = banks[result['item']['institution_id']]
            if bank: 
                ensure_icon(self.datadir, bank['name'],'bank',bank['logo'] if 'logo' in bank and bank['logo'] else None)
        if 'accounts' in result:
            if bank:
                for i in range(len(result['accounts'])):
                    result['accounts'][i]['institution_id'] = result['item']['institution_id']
                    result['accounts'][i]['item_id'] = result['item']['item_id']
            return result['accounts']
        else:
            return None
        
    def update_metadata(self, txns, merchants, categories):
        for txn in txns:
            if 'merchant_entity_id' in txn and txn['merchant_entity_id']:
                if txn['merchant_entity_id'] not in merchants:
                    merchants[txn['merchant_entity_id']] = {
                        'id': txn['merchant_entity_id'],
                        'name': txn['merchant_name'] if 'merchant_name' in txn else None,
                        'category_id': txn['category_id'],
                        'icon': txn['logo_url'] if 'logo_url' in txn else None,
                        'url': txn['website'] if 'website' in txn else None,
                        'categories': None
                    }
                ensure_icon(self.datadir, txn['merchant_name'],'merchant',txn['logo_url'])
        return merchants, categories

    def get_transactions(self, item, merchants, categories):
        done = False
        txns = []
        while(not done):
            data = {"access_token": item.get('access_token')}
            if 'txn_cursor' in item: data['cursor'] = item.get('txn_cursor')
            result = self.api(path="/transactions/sync", data=data)
            if 'added' in result:
                txns.extend(result['added'])
                self.update_metadata(result['added'], merchants, categories)
            if 'next_cursor' in result:
                item['txn_cursor'] = result['next_cursor']
            done = not result['has_more']
        #self.debug(txns)
        return txns
    
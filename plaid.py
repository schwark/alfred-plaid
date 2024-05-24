from workflow import web
import json
from common import get_category_icon, qnotify, get_merchant_icon, get_environment, get_bank_icon, get_stored_data, ICONS_DEFAULT, set_stored_data
from time import time

ERROR_MESSAGES = {
    'default': "Plaid API Error",
    'ITEM_LOGIN_REQUIRED': "Login needs updating"
}

class Plaid:
    def __init__(self, client_id, secret, user_id, wf):
        self.client_id = client_id
        self.secret = secret
        self.user_id = user_id
        self.environment = str(get_environment(wf))
        self.logger = wf.logger
        self.wf = wf
        
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
        else:
            result = r.json()
            if result and 400 == r.status_code and 'error_code' in result:
                error = ERROR_MESSAGES[result['error_code']] if result['error_code'] in ERROR_MESSAGES else ERROR_MESSAGES['default']
                qnotify('Plaid', error)
        self.debug(str(result))
        return result   
    
    def get_categories(self, wf):
        categories = {}
        icons = get_stored_data(wf, 'icons', ICONS_DEFAULT)
        result = self.api(path="/categories/get", data={}, no_auth=True)
        if 'categories' in result:
            for category in result['categories']:
                id = int(category['category_id'])
                #wf.logger.debug(f"{category['hierarchy']}:  {icon}")
                categories[id] = {
                    'id': id,
                    'list': category['hierarchy']
                }
                categories[id]['icon'] = get_category_icon(wf, id, categories, icons)
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
    
    def force_refresh(self, access_token):
        data = {"access_token": access_token}
        result = self.api(path="/transactions/refresh", data=data)
        return result

    def exchange_public_token(self, public_token):
        data = {"public_token": public_token}
        result = self.api(path="/item/public_token/exchange", data=data)
        return result
    
    def get_item(self, access_token):
        data = {"access_token": access_token}
        result = self.api(path="/item/get", data=data)
        return result['item'] if 'item' in result else None
    
    def del_item(self, access_token):
        data = {"access_token": access_token}
        result = self.api(path="/item/remove", data=data)
        return result
    
    def get_accounts(self, item, banks):
        icons = get_stored_data(self.wf, 'icons', ICONS_DEFAULT)
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
                bank['icon'] = get_bank_icon(self.wf, result['item']['institution_id'], banks, icons)
        if 'accounts' in result:
            if bank:
                for i in range(len(result['accounts'])):
                    result['accounts'][i]['institution_id'] = result['item']['institution_id']
                    result['accounts'][i]['item_id'] = result['item']['item_id']
            return result['accounts']
        else:
            return None
        
    def update_metadata(self, txns, merchants, icons):
        for txn in txns:
            if 'merchant_entity_id' in txn and txn['merchant_entity_id']:
                merchant_id = txn['merchant_entity_id']
                if merchant_id not in merchants:
                    merchants[merchant_id] = {
                        'id': merchant_id,
                        'name': txn['merchant_name'] if 'merchant_name' in txn else None,
                        'category_id': txn['category_id'],
                        'logo': txn['logo_url'] if 'logo_url' in txn else None,
                        'url': txn['website'] if 'website' in txn else None,
                        'categories': None
                    }
                    start = time()
                    merchants[merchant_id]['icon'] = get_merchant_icon(self.wf, merchant_id, merchants, icons)
                    self.logger.debug(f"{(time() - start):0.3f} to get merchant icon")
        return merchants

    def get_transactions(self, item, merchants):
        done = False
        txns = []
        icons = get_stored_data(self.wf, 'icons', ICONS_DEFAULT)
        while(not done):
            data = {"access_token": item.get('access_token')}
            if 'txn_cursor' in item: data['cursor'] = item.get('txn_cursor')
            result = self.api(path="/transactions/sync", data=data)
            if 'added' in result:
                txns.extend(result['added'])
                self.update_metadata(result['added'], merchants, icons)
            if 'next_cursor' in result:
                item['txn_cursor'] = result['next_cursor']
            done = not result['has_more']
        set_stored_data(self.wf, 'icons', icons)
        #self.debug(txns)
        return txns
    
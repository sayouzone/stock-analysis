class companydict:
    temp_dict = {
        '삼성전자': {
            'company': ['삼성전자', '삼전', 'SEC', 'SAMSUNG', 'samsung', 'Samsung', 'Samsung Electronics', '005930', '005930.KS', '005930.ks'],
            'code': '005930',
            'ticker': '005930.KS'
        },
        'SK하이닉스': {
            'company': ['SK하이닉스', 'sk하이닉스', '하이닉스', '000660', '000660.KS', '000660.ks'],
            'code': '000660',
            'ticker': '000660.KS'
         },
         '현대차': {
            'company': ['현대차', '현대자동차', '005380', '005380.KS', '005380.ks'],
            'code': '005380',
            'ticker': '005380.KS'
         },
        'NAVER': {
            'company': ['NAVER', 'naver', 'Naver', '네이버', '035420', '035420.KS', '035420.ks'],
            'code': '035420',
            'ticker': '035420.KS'
        },
        '셀트리온': {
            'company': ['셀트리온', '068270', '068270.KS', '068270.ks'],
            'code': '068270',
            'ticker': '068270.KS'
        },
        'AAPL': {
            'company': ['AAPL', 'Apple', 'apple', 'Apple Inc', '애플'],
            'code': 'AAPL',
            'ticker': 'AAPL'
        },
        'TSLA': {
            'company': ['TSLA', 'Tesla', 'tesla', 'Tesla Inc', '테슬라'],
            'code': 'TSLA', 
            'ticker': 'TSLA'
        },
        'GOOGL': {
            'company': ['GOOGL', 'Google', 'google', 'Alphabet', 'alphabet', '구글'],
            'code': 'GOOGL',
            'ticker': 'GOOGL'
        },
        'MSFT': {
            'company': ['MSFT', 'Microsoft', 'microsoft', '마이크로소프트'],
            'code': 'MSFT',
            'ticker': 'MSFT'
        },
        'PLTR': {
            'company': ['PLTR', 'Palantir', 'palantir', '팔란티어'],
            'code': 'PLTR',
            'ticker': 'PLTR'
        }
    }

    @staticmethod
    def get_code(user_input):
        for company_info in companydict.temp_dict.values():
            if user_input in company_info['company']:
                return company_info['code']
        return None
        
    @staticmethod
    def get_ticker(user_input):
        for company_info in companydict.temp_dict.values():
            if user_input in company_info['company']:
                return company_info['ticker']
        return None
    
    @staticmethod
    def get_company(user_input):
        for company_info in companydict.temp_dict.values():
            if user_input in company_info['company']:
                return company_info['company'][0]
        return None

    @staticmethod
    def get_company_by_code(code_input):
        for company_name, company_info in companydict.temp_dict.items():
            if code_input == company_info['code']:
                return company_name
        return None
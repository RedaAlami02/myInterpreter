"""Compare the port with actual legacy AST, without importing its SDK/runtime."""
import ast
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import fundamental_frame

ROOT=Path(__file__).resolve().parents[3]
source=ast.parse((ROOT/'cloud_function/functions/getprice/src/main.py').read_text())
constants=[node for node in source.body if isinstance(node,ast.Assign)
    and all(isinstance(target,ast.Name) for target in node.targets)
    and node.targets[0].id in {'PER_GREEN','PER_ORANGE','PEG_GREEN','PEG_ORANGE',
        'PR_GREEN','PR_ORANGE','PB_GREEN','PB_ORANGE','MAX_PER','MIN_TC5','MAX_TC5','MIN_ROE'}]
rate=next(node for node in source.body if isinstance(node,ast.FunctionDef) and node.name=='rate')
fit_chart=next(node for node in source.body if isinstance(node,ast.FunctionDef) and node.name=='fit_chart')
chart_scope={}
exec(compile(ast.Module(body=[fit_chart],type_ignores=[]),'legacy-chart','exec'),chart_scope)
loop=next(node for node in ast.walk(source) if isinstance(node,ast.For)
    and isinstance(node.target,ast.Tuple) and [v.id for v in node.target.elts]==['name','m'])
def assigned(node,key):
    return isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==key for t in node.targets)
start=next(i for i,node in enumerate(loop.body) if assigned(node,'cb'))
end=next(i for i,node in enumerate(loop.body) if assigned(node,'doc'))
legacy_code=compile(ast.Module(body=constants+[rate]+loop.body[start:end],type_ignores=[]),'legacy-price-math','exec')
legacy_doc=compile(ast.Module(body=[loop.body[end]],type_ignores=[]),'legacy-price-row','exec')
index_assignment=next(node for node in ast.walk(source) if assigned(node,'masi_doc'))
legacy_index=compile(ast.Module(body=[index_assignment],type_ignores=[]),'legacy-index-row','exec')


def legacy_ratios(price,company,market_cap):
    scope={'pa':price,'co':company,'m':{'market_cap':market_cap},'name':'fixture',
        'bpa':company.get('bpa') or 0,'tc5':company.get('tc5') or 0,'roe':company.get('roe') or 0,
        'na':company.get('na') or 0,'cp':company.get('cp') or 0,
        'context':SimpleNamespace(log=lambda *_:None),'log_error':lambda *_,**__:None,'db':None}
    exec(legacy_code,scope)
    values={key:scope[key] for key in ('cb','pb','per','peg','pr')}
    for key,green,orange in [('per',20,25),('peg',1,2),('pr',1.5,2),('pb',2,3)]:
        values[key+'_rating']=scope['rate'](scope[key],green,orange)
    return values


class PriceRatioParityTests(unittest.TestCase):
    def test_original_calculations_match_across_denominators_splits_and_rating_edges(self):
        base={'bpa':5,'tc5':10,'roe':20,'na':10000,'cp':500000,'net_profit':1}
        cases=[(100,base,None),(100,base,2000000),(100,dict(base,net_profit=-1),2000000),
            (100,dict(base,cp=-500000),None),(100,dict(base,tc5=.99),None),
            (100,dict(base,tc5=101),None),(100,dict(base,roe=.99),None),
            (100,dict(base,bpa=0,net_profit=0),None),(100,{},None),
            (100,dict(base,bpa=.001),None),(100,dict(base,na=0),None)]
        cases += [(price,dict(base,bpa=1,tc5=20,roe=10),None) for price in [0,20,25,26,500,501,-10]]
        for price,company,capital in cases:
            with self.subTest(price=price,company=company):
                self.assertEqual(fundamental_frame.price_ratios(price,company,capital),legacy_ratios(price,company,capital))

    def test_full_price_row_retains_legacy_columns_and_null_versus_zero(self):
        company={'bpa':5,'tc5':10,'roe':20,'na':10000,'cp':500000,'net_profit':1}
        for traded in (True,False):
            market={'symbol':'AAA','variation':0,'variation_v':0,'cours_ref':100,'open_price':99 if traded else None,
                'high':105 if traded else None,'low':98 if traded else None,'volume':0 if traded else None,
                'qty_traded':0 if traded else None,'market_cap':2000000 if traded else None,'data_chart':'1;2;3|R'}
            values=legacy_ratios(100,company,market['market_cap'])
            scope={**values,'pa':100,'name':'Company A','m':market,'now':'2026-10-29T12:00:00+00:00',
                'rate':lambda value,green,orange:None if value is None or value<=0 else 'green' if value<=green else 'orange' if value<=orange else 'red',
                'PER_GREEN':20,'PER_ORANGE':25,'PEG_GREEN':1,'PEG_ORANGE':2,'PR_GREEN':1.5,'PR_ORANGE':2,'PB_GREEN':2,'PB_ORANGE':3}
            exec(legacy_doc,scope)
            actual=fundamental_frame.price_document('Company A',100,company,market,scope['now'])
            self.assertEqual(actual,scope['doc'])
            self.assertEqual('volume' in actual,traded)
            if traded:self.assertEqual(actual['volume'],0)

    def test_row_does_not_invent_observation_time_or_store_nonpositive_price(self):
        for stamp in (None,'2026-10-29T12:00:00'):
            with self.assertRaises(ValueError):fundamental_frame.price_document('A',10,{}, {'symbol':'A'},stamp)
        for price in (0,-1,True,float('nan'),float('inf'),'10'):
            with self.assertRaises(ValueError):
                fundamental_frame.price_document('A',price,{}, {'symbol':'A'},'2026-10-29T12:00:00Z')

    def test_chart_trimming_matches_original_and_keeps_latest_points(self):
        for chart in ('1;2;3|R',';'.join(str(index) for index in range(200))+'|R',None,''):
            row=fundamental_frame.price_document('A',10,{}, {'symbol':'A','data_chart':chart},'2026-10-29T12:00:00Z')
            self.assertEqual(row.get('data_chart'),chart_scope['fit_chart'](chart) or None)

    def test_index_row_matches_original_without_stock_ratios_or_symbol(self):
        market={'cours_ref':1000,'variation':0,'variation_v':0,'high':1200,'low':900,
                'volume':0,'qty_traded':0,'market_cap':123456789}
        raw={}
        original_dict=index_assignment.value.generators[0].iter.func.value
        for key,value in zip(original_dict.keys,original_dict.values):
            if key.value in market:
                raw[value.args[0].args[0].value]=market[key.value]
        scope={'now':'2026-10-29T12:00:00Z','masi_cours':1100,'masi':raw,'num':lambda value:value}
        exec(legacy_index,scope)
        self.assertEqual(fundamental_frame.index_document('MASI',1100,market,scope['now']),scope['masi_doc'])


if __name__=='__main__':unittest.main()

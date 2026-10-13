import csv
import io
import json

def demo_csv(version='demo-v1'):
 rows=[]
 for i in range(200):
  person=f'虚构人物{i:03d}';company=f'示例星河{i:03d}科技有限公司';loc=f'虚构市示例路{i+1}号'
  reference=[person,company,loc]; predicted=reference.copy()
  case=i%10
  if case==3: predicted[0]=''
  if case==4: predicted[1]=f'星河{i:03d}科技'
  if case==5: predicted[2]='虚构市'
  if case==6: predicted[0]=person+'、虚构同伴'
  if case==7: predicted[1]='另一家虚构公司'
  if case==8: predicted[2]='示例新区'
  if case==9: predicted[0]=' '+person+' '
  if version=='demo-v2' and case in (3,5): predicted=reference.copy()
  rows.append({'event_id':f'SYN-{i:04d}','description':f'合成测试，非真实事件。{person}在{loc}到访{company}，该公司简称星河{i:03d}科技。',
   **{f'predicted_{f}':v for f,v in zip(('person','company','location'),predicted)},
   **{f'reference_{f}':v for f,v in zip(('person','company','location'),reference)},'model_version':version})
 stream=io.StringIO();w=csv.DictWriter(stream,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 return stream.getvalue().encode('utf-8-sig')

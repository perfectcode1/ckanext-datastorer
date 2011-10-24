from celery.task import task
import json
from messytables import CSVTableSet, XLSTableSet, types_processor, headers_guess, headers_processor, \
  offset_processor
import requests
import datetime

class WebstorerError(Exception):
    pass

def check_response_and_retry(response):
    try:
        if not response:
            raise WebstorerError('Webstore is not reponding')
    except Exception, e:
        webstorer_upload.retry(exc=e)

@task(name = "webstorer.upload", max_retries=24*7, default_retry_delay=3600)
def webstorer_upload(context, data):

    context = json.loads(context)
    data = json.loads(data)

    file_path = data['file_path']
    f = open(file_path, 'rb')          

    
    if file_path.split('.')[-1] == 'xls':
        table_sets = XLSTableSet.from_fileobj(f)
    else:
        table_sets = CSVTableSet.from_fileobj(f)

    ##only first sheet in xls for time being
    row_set = table_sets.tables[0]
    offset, headers = headers_guess(row_set.sample)
    row_set.register_processor(headers_processor(headers))
    row_set.register_processor(offset_processor(offset + 1))

    rows = []
    for row in row_set.dicts():
        for item in row:
            row[item] = unicode(row[item])
        rows.append(row)

    webstore_url = context.get('webstore_url').rstrip('/')
    webstore_request_url = '%s/%s/%s' % (webstore_url,
                                         context['username'],
                                         data['resource_id']
                                         )
    #check if resource is already there.
    webstore_response = requests.get(webstore_request_url+'.json')
    check_response_and_retry(webstore_response)

    #should be an empty list as no tables should be there.
    if json.loads(webstore_response.content):
        raise WebstorerError('Webstore already has this resource')

    response = requests.post(webstore_request_url+'/data',
                             data = json.dumps(rows),
                             headers = {'Content-Type': 'application/json',
                                        'Authorization': context['apikey']},
                             )
    check_response_and_retry(response)
    if response.status_code != 201:
        raise WebstorerError('Websore bad response code (%s). Response was %s'%
                             (response.status_code, response.content)
                            )

    ckan_url = context['ckan_url'].rstrip('/')
    ckan_request_url =  ckan_url + '/api/action/resource_update'

    ckan_resource_data = {
        'id': data["resource_id"],
        'webstore_url': webstore_request_url+'/data',
        'webstore_last_updated': datetime.datetime.now().isoformat()
    }

    response = requests.post(
        ckan_request_url,
        data=json.dumps(ckan_resource_data),
        headers = {'Content-Type': 'application/json',
                   'Authorization': context['apikey']},
        )
    
    


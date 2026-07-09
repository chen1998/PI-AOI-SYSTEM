import requests
import datetime

def send_mail(request_body):
    session_requests = requests.session()
    headers = {
        'Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Encoding':'gzip, deflate, br',
        'Accept-Language':'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
        'Content-Type':'application/soap+xml; charset=utf-8',
        'User-Agent':'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.94 Safari/537.36'
        }

    data = """<?xml version="1.0" encoding="utf-8"?>
    <soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
      <soap12:Body>
        <ManualSend_07 xmlns="http://tempuri.org/">
          <strMailCode>rJJeeO5U0ZI=</strMailCode>
          <strRecipients>%s</strRecipients>
          <strCopyRecipients>%s</strCopyRecipients>
          <strSubject>%s</strSubject>
          <strBody>%s</strBody>
        </ManualSend_07>
      </soap12:Body>
    </soap12:Envelope>""" 
    URL = 'https://ids.cdn.corpnet.auo.com/IDS_WS/Mail.asmx'
    import xml.sax.saxutils
    # Assuming request_body is a dictionary containing the necessary data
    # Encode the innerHTML of the table
    request_body['strBody'] = xml.sax.saxutils.escape(request_body['strBody'])
    # Construct the SOAP request data
    soap_data = data % (request_body['strRecipients'], request_body['strCopyRecipients'], 
                        request_body['strSubject'], request_body['strBody'])
    # Make the POST request
    proxies = {'http': 'http://10.97.4.1:8080', 'https': 'http://10.97.4.1:8080'}
    result = session_requests.post(URL, data=soap_data.encode('utf-8'), headers=headers, proxies=proxies, verify=False)

    return result

if __name__ == '__main__':
    now = datetime.datetime.now()
    time_now = now.strftime("%Y-%m-%d %H:%M:%S")
    strBody = "<a href='http://10.97.142.217:8204/'>PI AOI System 連結</a><br>" #br換行
    strBody += time_now+" NG率超標機台：<br>"
    strBody += "line_id_key[line_id]"+", NG率:"+str(6)+"%, 片數:"+str(45)+", OK數:"+str(23)+", NG數:"+str(77)
    strBody += ", 坵Mura數:"+str(456)+", 縱Mura數:"+str(456)+", 橫Mura數:"+str(456)+", Other Mura數:"+str(456)+"<br>"
    post_data = {
                'strRecipients': 'ruby.yc.lin@auo.com', #收件人，多人使用;分開 耀中部門改成DL6AN1@auo.com
                'strCopyRecipients': 'harry.lin@auo.com', #CC名單
                'strSubject': 'PI AOI System 偵測爆點請盡速確認', #titile
                'strBody': strBody #檔案內容
            }

    send_mail(post_data)



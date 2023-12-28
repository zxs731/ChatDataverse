import streamlit as st
from dotenv import load_dotenv  
import os


if "key" not in st.session_state:
    st.session_state.key = None
if "token" not in st.session_state:
    st.session_state.token = None


key = st.sidebar.text_input("Your key", type="password")
token = st.sidebar.text_input("Your token", type="password",value="")    
if not key:
    st.info("Please add your Azure Open AI Key to continue.")
else:
    st.session_state.key=key    


if not token:
    st.info("Please add your dynamics 365 CRM authorization token to continue.")
else:
    st.session_state.token=token    

if not key or not token:
    st.stop()
    
import json, ast
#from openai import OpenAI
import openai


# 加载.env文件  
load_dotenv("en1106.env")  

os.environ["OPENAI_API_TYPE"] = os.environ["Azure_OPENAI_API_TYPE1"]
os.environ["OPENAI_API_BASE"] = os.environ["Azure_OPENAI_API_BASE1"]
os.environ["OPENAI_API_KEY"] =  st.session_state.key
os.environ["OPENAI_API_VERSION"] = os.environ["Azure_OPENAI_API_VERSION1"]
BASE_URL=os.environ["OPENAI_API_BASE"]
API_KEY=os.environ["OPENAI_API_KEY"]

CHAT_DEPLOYMENT_NAME=os.environ.get('AZURE_OPENAI_API_CHAT_DEPLOYMENT_NAME')
EMBEDDING_DEPLOYMENT_NAME=os.environ.get('AZURE_OPENAI_API_EMBEDDING_DEPLOYMENT_NAME')

openai.api_type = os.environ["OPENAI_API_TYPE"]
openai.api_base = os.environ["OPENAI_API_BASE"]
openai.api_version = "2023-07-01-preview"
openai.api_key = os.getenv("OPENAI_API_KEY")
# LLM
import requests
from urllib.parse import quote  
  



def queryRecords(tableLogicNames,fetchXml):
    # 定义Dynamics 365实例的URL和API版本
    url = "https://udkanzai-dev1.crm7.dynamics.com/api/data/v9.2/"
    # 定义请求头，包括OAuth认证信息和内容类型
    headers = {  
        'Content-Type': 'application/xml',  
        'Accept': 'application/json',  
        'OData-MaxVersion': '4.0',  
        'OData-Version': '4.0', 
        "Authorization": f'Bearer {st.session_state.token}',

    }  
    fetchxml_encoded = quote(fetchXml)  
    response = requests.get(f'{url}{tableLogicNames}?fetchXml={fetchxml_encoded}', headers=headers)  
    # 处理响应
    if response.status_code == 200:
        #data = response.json()
        return response.text
    else:
        return f'查询失败:{response.text}'

def run_conversation(prompt,feedback):
    # Step 1: send the conversation and available functions to the model
    messages = [{"role":"system","content":'''Our purchase system is customized based on Dynamics 365. Its information as below,
Organization: https://udkanzai-dev1.crm7.dynamics.com"
Table logic name: msdyn_purchaseorder Description: Purchase Order
    column logic name: createdby Description: The creator's user id which is the systemuser table's systemuserid

Table logic name: systemuser Description: User

    '''}]
    
    for msg in st.session_state.messages[-10:]:
        if msg["role"]=="user":
            messages.append({ "role": "user","content": msg["content"]})
        elif msg is not None and msg["content"] is not None:
            messages.append({ "role": "assistant", "content":msg["content"]})
       
    tools = [
        {
            "type": "function",
            "function": {
                "name": "queryRecords",
                "description": "query records or table from our CRM dataverse",
                "parameters": {
                    "type": "object",
                    "properties": {
                      "tableLogicNames": {
                        "type": "string",
                        "description": "The logic name of query table which is in the url route. It should be the plural of the logic name."
                      },
                      "fetchXml": {
                        "type": "string",
                        "description": "The fetchXml of query."
                      }
                    },
                    "required": ["tableLogicNames","fetchXml"],
                },
            },
        }
    ]
    print(messages)
    response = openai.ChatCompletion.create(
        engine="gpt-35-turbo-1106",
        messages = messages,
        temperature=0.7,
        max_tokens=800,
        top_p=0.95,
        frequency_penalty=0,
        presence_penalty=0,
        stop=None,
        tools=tools,
        tool_choice="auto",  # auto is default, but we'll be explicit
        stream=True
    )
    ret=''
    function_name=''
    funArg=''
    callId=None
    for chunk in response:
        print(chunk)
        if chunk.choices:
            if 'content' in chunk.choices[0].delta:
                c=chunk.choices[0].delta.content
                ret+=c
                feedback(ret)
            if "tool_calls" in chunk.choices[0].delta:
                if 'id' in chunk.choices[0].delta.tool_calls[0]:
                    callId=chunk.choices[0].delta.tool_calls[0].id
                if 'function' in chunk.choices[0].delta.tool_calls[0]:
                    if 'name' in chunk.choices[0].delta.tool_calls[0].function:
                        function_name=chunk.choices[0].delta.tool_calls[0].function.name
                    if 'arguments' in chunk.choices[0].delta.tool_calls[0].function:   
                        funArg+=chunk.choices[0].delta.tool_calls[0].function.arguments
                    
                
    if ret !='':
        return ret

    print(callId)
    print(function_name)
    print(funArg)
    
    # Step 2: check if the model wanted to call a function
    if function_name !='':
        assistant_reply={
          "role": "assistant",
          "tool_calls": [
            {
              "id":callId,
              "type": "function",
              "function": {
                "name": function_name,
                "arguments":funArg
              }
            }
          ],
          "content":" "
        }
       
        # Step 3: call the function
        # Note: the JSON response may not always be valid; be sure to handle errors
        available_functions = {
            queryRecords.__name__: queryRecords,
        }  # only one function in this example, but you can have multiple
        function_args = json.loads(funArg)
        function_to_call = available_functions[function_name]
        function_response = function_to_call(**function_args)
        messages.append(assistant_reply)  # extend conversation with assistant's reply
        # Step 4: send the info for each function call and function response to the model
        messages.append(
                {
                    "tool_call_id": callId,
                    "role": "tool",
                    "name": function_name,
                    "content": function_response,
                }
            )  # extend conversation with function response
        
            
        #print(messages)
        second_response = openai.ChatCompletion.create(
            engine="gpt-35-turbo-1106",
            messages = messages,
            temperature=0.7,
            max_tokens=800,
            top_p=0.95,
            frequency_penalty=0,
            presence_penalty=0,
            stop=None,
            tools=tools,
            tool_choice="auto",  # auto is default, but we'll be explicit
            stream=True
        )  # get a new response from the model where it can see the function response
        ret=''
        for chunk in second_response:
            print(chunk)
            if chunk.choices:
                if 'content' in chunk.choices[0].delta:
                    c=chunk.choices[0].delta.content
                    ret+=c
                    feedback(ret)
        return ret


if "messages" not in st.session_state:
    st.session_state.messages = []

    
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

def writeReply(cont,msg):
    cont.text(msg)

if prompt := st.chat_input():
    st.chat_message("user").write(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("assistant"):
        p=st.empty()
        re = run_conversation(prompt,lambda x:writeReply(p,x))
        print(re)
        st.session_state.messages.append({"role": "assistant", "content": re})
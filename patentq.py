# importing library methods
from llm_axe.agents import FunctionCaller
from llm_axe.models import OllamaChat
import time
from llm_axe.core import AgentType
from llm_axe.agents import Agent
import ast
from patent_client import Patent, PublishedApplication, Inpadoc
import pandas as pd
import re

# Function to extract application number from text

# Function to extract patent number from text
def extract_patent_number(text):
    # Define the regex pattern
    pattern = r'(?:US|EP)\s?-?\d{4,}\s?-?(?:A\d+|B\d+)?'
    
    # Search for matches in the text
    match = re.search(pattern, text)
    
    # Return the matched patent number or None if not found
    return match.group() if match else None

class USPTO():
    def __init__(self, input_application_id=None, prompt=''):
        self.input_application_id = input_application_id
        self.input_application_id = self.id_cleanup()
        self.prompt = prompt
        if len(self.input_application_id) != 8 and len(self.input_application_id) != 11:
            self.input_application_id = extract_patent_number(prompt)
            self.input_application_id = self.id_cleanup()
            # print(f'extracted id: {self.input_application_id}')
        
    
    def get_application_id(self):
        return self.input_application_id
    
    def patent_to_df(self, data):
            try:
                # Ensure input is a dictionary
                if not isinstance(data, dict):
                    raise ValueError("Input needs to be a dictionary.")
                
                df = pd.DataFrame()

                for key in data:
                    try:
                        # Only add to DataFrame if data[key] is not None or empty
                        if data[key]:
                            if isinstance(data[key], dict):
                                for subkey in data[key]:
                                    df[subkey] = [data[key][subkey]]
                            else:  
                                df[key] = [data[key]]
                    except Exception as e:
                        print(f"Error processing key '{key}': {e}")
                        continue

                return df  # Return after the loop completes

            except ValueError as ve:
                print(ve)
                return pd.DataFrame()  # Return an empty DataFrame in case of invalid input
    
    # remove kind code from input application id
    def id_cleanup(self):
        self.input_application_id = str(self.input_application_id)
        self.input_application_id = self.input_application_id.strip()
        if self.input_application_id[-2].isalpha():
            self.input_application_id = self.input_application_id[:-2]
        if self.input_application_id.startswith('US') or self.input_application_id.startswith('EP'):
                self.input_application_id = self.input_application_id[2:]
        self.input_application_id = self.input_application_id.replace(' ', '')
        print(f'cleaned up id: {self.input_application_id}')
        return self.input_application_id
    
    # get patent data
    def get_patent_text(self):
        if self.input_application_id:
            if len(self.input_application_id) == 11 and self.input_application_id.isnumeric():
                published_application = PublishedApplication.objects.get(self.input_application_id)
                pubdict = published_application.to_dict()
                df = self.patent_to_df(pubdict)
                print(df.head())
                return df
            
            elif len(self.input_application_id) == 8 and self.input_application_id.isnumeric():
                patented_application = Patent.objects.get(self.input_application_id)
                patdict = patented_application.to_dict()
                df = self.patent_to_df(patdict)
                return df
            
            else:
                return 'Invalid application number'             
        else:
            return 'No application number provided'
            
    def pat_response(self, llm, df):
        context_prompt = f"""Determine from this list of column names {df.columns} the column(s) that is needed to answer the following query: {self.prompt}. Reply only in a python list format in order of relevance.
        """
        if self.prompt:
            generic_responder_init = Agent(llm, agent_type=AgentType.GENERIC_RESPONDER, temperature=0.3)
            resp = generic_responder_init.ask(context_prompt)
            resp = ast.literal_eval(resp)
            con_resp = ''
            for item in resp:
                con_resp += f'{item}: {df[item][0]}; '
            # print(resp, '\n')
            new_prompt = f"""{self.prompt}: context: {con_resp}"""
            
            # print(new_prompt)
            generic_responder_sec = Agent(llm, agent_type=AgentType.GENERIC_RESPONDER)
            fin_response = generic_responder_sec.ask(new_prompt)
            # print(fin_response)
            return fin_response
        else:
            return 'No prompt provided'



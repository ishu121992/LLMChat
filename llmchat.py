#!/usr/bin/env python3
import ollama
from nicegui import ui
from starlette.formparsers import MultiPartParser
import asyncio
import re
import patentq
from llm_axe.agents import FunctionCaller
from llm_axe.models import OllamaChat
import asyncio

MultiPartParser.max_file_size = 1024 * 1024 * 5  # 5 MB max file size

# Function to get the application number
def get_application_number():
    "extract the application number in numeric format or alphanumeric format irrespective of whether it has comma, slash, or backslash. The number of digits in the application number should be 11 or 8."
    return ""

# Create a class to run chat with conversation history using Ollama
class LLMChat:
    def __init__(self):
        self.messages = []
        self.role = ['user', 'assistant']
        self.models = [item for item in [ollama.list()['models'][i]['model'] for i in range(len(ollama.list()['models']))] if item.find('emb') < 0]
        self.models.extend(['openai-gpt4o-turbo', 'claudeai/claudeai-turbo', 'geminai/geminaio-turbo'])  # adding 3rd party models
        self.model = self.models[0]
        self.df = None  # Initialize the DataFrame to None
        self.application_number = ''  # Store the current application number
        ollama.chat(model=self.model, keep_alive=True)
        self.llm = OllamaChat(model=self.model)
    
    async def set_model(self, value):
        self.model = value
        resp = ollama.chat(model=self.model, keep_alive=True)  # Assuming this might be a blocking operation
        if resp['done']:
            ui.notify(f"Model {self.model} is loaded and ready for chat")
        else:
            ui.notify(f"Error loading model {self.model}")

    def add_history(self, content, role):
        self.messages.append({'role': role, 'content': content})

    def generate_chunks(self, text, chunk_size=20):
        # Split the text into chunks of the specified size
        for i in range(0, len(text), chunk_size):
            # await asyncio.sleep(0)  # Yield control back to the event loop
            yield {"message": {"content": text[i:i + chunk_size]}}  # Create the expected chunk format

    async def async_patent_call(self, question=''):
        """Handles the patent-related calls asynchronously and yields chunks."""
        # Use FunctionCaller to extract the application number from the question
        extracted_application_number = ''
        fc = FunctionCaller(self.llm, [get_application_number], temperature=0.3)
        result = await asyncio.to_thread(fc.get_function, question)  # Run in a separate thread to prevent blocking

        if result:
            params = result['parameters']
            extracted_application_number = params['application_number']
        if extracted_application_number == '':
            uspto = patentq.USPTO(self.application_number, question)
            final_application_number = uspto.get_application_id()
            print(f"Final application number: {final_application_number}")
        else:
            uspto = patentq.USPTO(extracted_application_number, question)
            final_application_number = uspto.get_application_id()
            print(f"Final application number: {final_application_number}")
        
        if final_application_number != self.application_number:
            self.application_number = final_application_number  # Update the stored application number
            self.df = await asyncio.to_thread(uspto.get_patent_text)  # Fetch new patent data
            # Generate the model reply based on the DataFrame
            model_reply = await asyncio.to_thread(uspto.pat_response, self.llm, self.df)  # Make the response generation async
            self.add_history(model_reply, self.role[1])
        else:
            print("Reusing the existing DataFrame")

            # Generate the model reply based on the DataFrame
            model_reply = await asyncio.to_thread(uspto.pat_response, self.llm, self.df)  # Make the response generation async
            self.add_history(model_reply, self.role[1])


        # Use async generator to yield chunks
        for chunk in self.generate_chunks(model_reply):
            await asyncio.sleep(0)  # Yield control back to the event loop
            yield chunk

    async def async_ollama_call(self, question=''):
        self.add_history(question, self.role[0])

        if question.startswith('@patent'):
            question = question.replace('@patent', '').strip()
            async for chunk in self.async_patent_call(question):
                yield chunk
        else:
            def sync_chat_generator():
                return ollama.chat(model=self.model, messages=self.messages, stream=True)
            
            # Wrap the synchronous generator in an asynchronous one
            sync_gen = sync_chat_generator()
            
            for chunk in sync_gen:
                await asyncio.sleep(0)  # Yield control back to the event loop
                yield chunk



def render_response(response, response_message):
    # Match only multi-line code blocks (```code```)
    pattern = r'```[\s\S]*?```'

    # Split the response into parts: code and non-code
    parts = re.split(pattern, response)
    codes = re.findall(pattern, response)

    for index, part in enumerate(parts):
        # Non-code part
        if part.strip():
            ui.markdown(part).classes('text-sm')

        # Code block (if available)
        if index < len(codes):
            code = codes[index].strip('```')
            ui.code(code).classes('bg-gray-100 p-2 rounded-lg')

chat_instance = LLMChat()  # New instance created here

@ui.page('/')
def main():
    ui.add_css("""
    .q-message-text--received {
        color: #f3f4f6;
        border-radius: 4px 4px 4px 0;
    }
    .q-uploader__title {
        font-size: small;
        font-weight: 500;
        line-height: normal;
        word-break: break-word;
        color: #000000;
    }
    .q-uploader__list {
        position: relative;
        border-bottom-left-radius: inherit;
        border-bottom-right-radius: inherit;
        padding: 0px;
        min-height: 0px;
    }
    .q-layout__section--marginal {
        background-color: var(--q-primary);
        color: #000000;
    }
               
    /* Tick mark styling */
    .tick {
        display: none;
        color: green;
        font-size: 16px;
        margin-left: 4px;
    }

    /* Show tick mark */
    .tick.show {
        display: inline;
    }
               
    #c9 .max-w-2xl {
    max-width: min-content;
    }
    """)

    async def send() -> None:
        question = text.value
        text.value = ''

        with message_container:
            ui.chat_message(text=question, name='You', sent=True)
            response_message = ui.chat_message(name='Bot', sent=False)
            spinner = ui.spinner(type='dots')

        stream = chat_instance.async_ollama_call(question=question)  # Get the async generator
        
        response = ''
        async for chunk in stream:
            response += chunk['message']['content']
            response_message.clear()
            with response_message:
                # Render the response as Markdown
                render_response(response, response_message)
                # Add the copy-to-clipboard button in grey color
                ui.button('Copy', color='grey', on_click=lambda: ui.clipboard.write(response)).props('rounded')

            ui.run_javascript('window.scrollTo(0, document.body.scrollHeight)')

        message_container.remove(spinner)
        if response:
            chat_instance.add_history(response, 'assistant')  # Call add_history on the instance

    ui.add_css(r'a:link, a:visited {color: inherit !important; text-decoration: none; font-weight: 500}')

    ui.query('.q-page').classes('flex')
    ui.query('.nicegui-content').classes('w-full')

    # Function to select model
    def select_model(value):
        model = value.value
        return model
    mode_text = ["Patent Search On", "Web Search On", "Doc Chat On", "Image Chat On"]
    key_words = ["@patent", "@web", "@doc", "@image"]
    zip_mode = dict(zip(key_words, mode_text))
    
    with ui.tabs().classes('w-full') as tabs:
        ui.tab('Chat', label='Chat', icon='chat')
        ui.tab('Settings', label='Settings', icon='settings')
    with ui.tab_panels(tabs, value='Chat').classes('w-full max-w-2xl mx-auto flex-grow items-stretch'):
        message_container = ui.tab_panel('Chat').classes('items-stretch')
        with ui.tab_panel('Settings').classes('items-stretch'):
            ui.label('Select model:').classes('mx-3' 'text-lg')
            ui.select(chat_instance.models, value=chat_instance.models[0]).bind_value(select_model)
            ui.button('Set model', on_click=lambda: chat_instance.set_model(select_model.value))
    
    with ui.footer().classes('bg-white'), ui.column().classes('w-full max-w-3xl mx-auto my-6'):
        with ui.row().classes('w-full no-wrap items-center'):
            # Ensure result is initialized before referencing
            result = ui.label().classes('mx-3 text-gray-500 font-semibold')

            # Adjust the input field to handle mode selection based on the keyword in the text
            text = ui.input(
                placeholder="Enter your question",
                on_change=lambda e: update_result_label(e.value)  # Pass the value to update function
            ).props('rounded outlined input-class=mx-3').props('clearable').classes('w-full self-center').on('keydown.enter', send)

            # Define the function to handle updates
            def update_result_label(value):
                # Check if any special keyword exists in the input, regardless of its position
                matched_mode = next((mode for keyword, mode in zip_mode.items() if keyword in value), None)
                
                if matched_mode:
                    # If a keyword is found, display the corresponding mode text
                    result.set_text(matched_mode)
                    result.classes('text-green-500')  # Apply classes separately
                else:
                    # If no keyword is found, clear the label
                    result.set_text('')

            ui.upload(on_upload=lambda e: ui.notify(f'Uploaded {e.name}')).classes('max-w-full')

        # adding row to the footer to show selected model
        with ui.row().classes('w-full no-wrap items-center'):
            ui.label(f'Selected model: {select_model.value}').classes('mx-3' 'text-gray-500' 'font-semibold')


ui.run(title='Chat with Ollama (example)')
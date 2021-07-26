# Copyright 2017-2018 IBM Corp. All Rights Reserved.
# See LICENSE for details.
#
# Author: Henrik Loeser
#
# Converse with your assistant based on IBM Watson Assistant service on IBM Cloud.
# See the README for documentation.
#

import json, argparse, importlib, peruse, subprocess
from os.path import join, dirname
from ibm_watson import AssistantV2
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator

privcontext=None
assistantService=None
with open("config.json") as confFile:
    config = json.load(confFile)
    assistantID = config['id']

def loadAndInit(confFile=None):
    # Credentials are read from a file
    with open(confFile) as confFile:
        config = json.load(confFile)
        configWA = config['credentials']
    global assistantService
    # Initialize the Watson Assistant client, use API V2
    if 'apikey' in configWA:
        # Authentication via IAM
        authenticator = IAMAuthenticator(configWA['apikey'])
 
        assistantService = AssistantV2(
            authenticator=authenticator,
            version=configWA['versionV2'])
        assistantService.set_service_url(configWA['url'])
    else:
        print('Expected apikey in credentials.')
        exit


# Define parameters that we want to catch and some basic command help
def initParser(args=None):
    parser = argparse.ArgumentParser(description='Watson Assistant tool',
                                     prog='assistant.py',
                                     usage='%(prog)s [-h | -dialog ] [options]')
    parser.add_argument("-dialog",dest='dialog', action='store_true', help='have dialog')
    parser.add_argument("-outputonly",dest='outputOnly', action='store_true', help='print dialog output only')
    parser.add_argument("-id",dest='assistantID', default=assistantID, help='Assistant ID')
    parser.add_argument("-actionmodule",dest='actionModule', help='Module for client action handling')
    parser.add_argument("-context",dest='context', help='context file')
    parser.add_argument("-config",dest='confFile', default='config.json', help='configuration file')

    return parser


# Start a dialog and converse with Watson
def converse(assistantID, outputOnly=None, contextFile=None):
    contextFile="session_contextV2.json"
    print ("Starting a conversation, stop by Ctrl+C or saying 'bye'")
    print ("======================================================")
    # Start with an empty context object
    context={}
    first=True

    ## Load conversation context on start or not?
    contextStart = input("Start with empty context? (y/n)\n")
    if (contextStart == "n" or contextStart == "N"):
        print ("loading old session context...")
        with open(contextFile) as jsonFile:
            context=json.load(jsonFile)
            jsonFile.close()

    # create a new session
    response = assistantService.create_session(assistant_id=assistantID).get_result()
    sessionID = response['session_id']
    print('Session created!\n')

    resp=assistantService.message(assistant_id=assistantID, session_id=sessionID,).get_result()
    if (outputOnly):
        for responses in resp['output']['generic']:
            if "text" in responses:
                print(json.dumps(responses["text"], indent=2)[1:-1])
                peruse.textTospech(json.dumps(responses["text"], indent=2)[1:-1])
            if "title" in responses:
                print(json.dumps(responses["title"], indent=2)[1:-1])
                peruse.textTospech(json.dumps(responses["title"], indent=2)[1:-1])
                for options in responses["options"]:
                    print(json.dumps(options["label"], indent=2)[1:-1])
                    peruse.textTospech(json.dumps(responses["label"], indent=2)[1:-1])
    else:
        print ("")
        print ("Full response object:")
        print ("---------------------")
        print(json.dumps(resp, indent=2))


    # Now loop to chat
    while True:
        # get some input

        subprocess.call(["python", "transcribe.py", "-t", "5"])
        file2read = open("speech.txt", 'r')
        text = file2read.readline()
        file2read.close()
        minput = text
        # if we catch a "bye" then exit after deleting the session
        if (minput == "bye"):
            response = assistantService.delete_session(
                assistant_id=assistantID,
                session_id=sessionID).get_result()
            print('Session deleted. Bye...')
            break

        # Read the session context from file if we are not entering the loop
        # for the first time
        if not first:
            try:
                with open(contextFile) as jsonFile:
                    context=json.load(jsonFile)
            except IOError:
                # do nothing
                print ("ignoring")
            else:
                jsonFile.close()
        else:
            first=False

        # Process IBM Cloud Function credentials if present
        if privcontext is not None:
            context.update(privcontext)

        # send the input to Watson Assistant
        # Set alternate_intents to False for less output
        resp=assistantService.message(assistant_id=assistantID,
                                session_id=sessionID,
                                 input={'text': minput,
                                 'options': {'alternate_intents': True, 'return_context': True, 'debug': True}}

                                 ).get_result()
        #print(json.dumps(resp, indent=2))

        # Save returned context for next round of conversation
        if ('context' in resp):
            context=resp['context']


        respOutput=resp['output']

        if ('actions' in respOutput and len(respOutput['actions']) and respOutput['actions'][0]['type']=='client'):
            # Dump the returned answer
            if not outputOnly:
                print ("")
                print ("Full response object of intermediate step:")
                print ("------------------------------------------")
                print(json.dumps(resp, indent=2))

            if (hca is not None):
                contextNew=hca.handleClientActions(context,respOutput['actions'], resp)

                # call Watson Assistant with result from client action(s)
                resp=assistantService.message(assistant_id=assistantID,
                                 session_id=sessionID,
                                 input={'text': minput,
                                 'options': {'alternate_intents': True, 'return_context': True, 'debug': True}},
                                 intents=respOutput['intents'],
                                 context=contextNew).get_result()
                context=resp['context']
                respOutput=resp['output']
            else:
                print("\n\nplease use -actionmodule to define module to handle client actions")
                break


        # Dump the returned answer
        if (outputOnly):
            print ("Response:")
            for responses in respOutput['generic']:
                if "text" in responses:
                    print(json.dumps(responses["text"], indent=2)[1:-1])
                    peruse.textTospech(json.dumps(responses["text"], indent=2)[1:-1])
        else:
            print ("")
            print ("Full response object:")
            print ("---------------------")
            print(json.dumps(resp, indent=2))

        # Persist the current context object to file.
        with open(contextFile,'w') as jsonFile:
            json.dump(context, jsonFile, indent=2)
        jsonFile.close()


#
# Main program, for now just detect what function to call and invoke it
#
if __name__ == '__main__':
    # Assume no module for client actions
    hca=None

    # initialize parser
    parser = initParser()
    parms =  parser.parse_args()
    # enable next line to print parameters
    # print parms

    # load configuration and initialize Watson
    loadAndInit(confFile=parms.confFile)

    if (parms.dialog):
        if parms.actionModule:
            hca=importlib.import_module(parms.actionModule)
        converse(parms.assistantID, parms.outputOnly)
    else:
        parser.print_usage()

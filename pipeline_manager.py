#! /usr/bin/python
# -*- coding:utf-8 -*-

from flask import Flask, request
import json
import jenkins
from lxml import etree
import requests
from pathlib import Path

########################
# global configuration #
########################

jenkinsServerURL = "http://IP:PORT"

######################
# file configuration #
######################

# file used to store bitbucket credentials
bitbucket_credentials_filename = '.bbcredz'

# file used to store a cache of the available repositories
repositoryCacheFileName = 'repository_cache.json'

# file used to store a cache of availabble branches
branchesCacheFileName = 'branches_cache.json'

# file used to store pipelines configuration
pipeline_list_filename = 'pipelines.json'

# port on wich the flask server listen
listenPort = 8081

#############################
# jenkins related functions #
#############################

# get the list of jobs' name configured on jenkins
def _getAvailablejobs(server):
  availableJobs = server.get_jobs()
  jobs = []
  for job in availableJobs:
    jobs.append(job['fullname'].encode('utf-8'))
  return json.dumps(jobs)

# get parameters of a given jenkins job
def _getJobParameters(server, jobName):
  config = etree.fromstring(server.get_job_config(jobName).encode('utf-8'))
  jobParameters = {}
  paramtersPath = '/project/properties/hudson.model.ParametersDefinitionProperty/parameterDefinitions'
  for parameterDefinitions in config.xpath(paramtersPath):
    for parameter in parameterDefinitions:
      if parameter.tag == 'hudson.model.ChoiceParameterDefinition':
        jobParameters[parameter.find('name').text] = {'description': parameter.find('description').text, 'type': 'choices', 'values': []}
        choices = parameter.getiterator()
        for choice in choices:
          if choice.tag == 'string':
            jobParameters[parameter.find('name').text]['values'].append(choice.text)
      if parameter.tag == 'hudson.model.StringParameterDefinition':
        jobParameters[parameter.find('name').text] = {'description': parameter.find('description').text, 'type': 'text', 'values': [ parameter.find('defaultValue').text ] }
  return json.dumps(jobParameters)

# start a job described in a pipeline on a jenkins server
def _startJenkinsJob(server, pipeline):
  parameters = {}
  jobName = pipeline['job']
  for parameter in pipeline['parameters']:
    parameters[parameter] = pipeline['parameters'][parameter]
  if not bool(parameters):
    try:
      server.build_job(jobName, parameters=None, token=None)
    except:
      print 'E: impossible to start the pipeline '+str(pipeline)
      return '{ "error": "impossible to start the pipeline '+json.dumps(pipeline)+'" }'
  try:
    print 'OK job sent'
    server.build_job(jobName, parameters, token=None)
  except:
    print 'E: impossible to start the pipeline '+str(pipeline)
    return '{ "error": "impossible to start the pipeline '+json.dumps(pipeline)+'" }'
  return '{ "OK": pipeline started job '+str(pipeline['job'])+'"}'

#########################
# git related fucntions #
#########################

# check if connection to bitbucket, return credentials if OK
def _connectToBitbucket(credentials):
  if Path(credentials).is_file():
    bitbucketCredentialsFile = open(credentials, 'r')
  else:
    print "E: can't open "+credentials
    return "{ can't open "+credentials+' }'
  for line in bitbucketCredentialsFile.readlines():
    if 'user: ' in line:
      bbUser = line[6:].rstrip()
    if 'pass' in line:
      bbPass = line[6:].rstrip()
    if 'slug' in line:
      bbSlug = line[6:].rstrip()
  bitbucketCredentialsFile.close()
  if 'bbUser' in locals() and 'bbPass' in locals() and 'bbSlug' in locals():
    response = requests.get('https://api.bitbucket.org/2.0/repositories/'+bbSlug, auth=(bbUser, bbPass))
    if response.status_code != 200:
      print 'E: invalid bitbucket credentials stored in '+credentials
      return '{ "error": "invalid bitbucket credentials stored in '+credentials+'" }'
  else:
    print "E: can not read credentials from "+credentials+'\nthis file sould contain : \nuser: "username"\npass: "password"\nslug: "company slug"\n'
    return '{ "error": "can not read credentials from '+credentials+'this file sould contain : user: username pass: password slug: company_slug" }'
  return bbUser, bbPass, bbSlug

# list available repositories on bitbucket and their corresponding API URLs
def _getAvailableRepos(useCache):
  repositories = {}
  if Path(repositoryCacheFileName).is_file() and useCache:
    repositoryCacheFile = open(repositoryCacheFileName, "r")
    repositories = json.load(repositoryCacheFile)
    repositoryCacheFile.close()
    print 'repository list read from cache'
    return json.dumps(repositories)
  response = [requests.get('https://api.bitbucket.org/2.0/repositories/'+bitbucketSlug, auth=(bitbucketUser, bitbucketPass))]
  if response[-1].status_code != 200:
    return
  content = [response[-1].json()]
  while 'next' in content[-1]:
    response.append(requests.get(content[-1]['next'], auth=(bitbucketUser, bitbucketPass)))
    content.append(response[-1].json())
  for page in content:
    for repos in page['values']:
      repositories[repos['name']] = repos['links']['branches']['href']
  repositoryCacheFile = open(repositoryCacheFileName, 'w')
  repositoryCacheFile.write(json.dumps(repositories))
  repositoryCacheFile.close()
  print 'repository cache created'
  return json.dumps(repositories)

# list available branches forr a given repository
def _getAvailableBranches(repo, useCache):
  repositoryBranches = []
  if repo not in availableRepositories:
    return
  response = [requests.get(availableRepositories[repo], auth=(bitbucketUser, bitbucketPass))]
  if response[-1].status_code != 200:
    return
  content = [response[-1].json()]
  while 'next' in content[-1]:
    response.append(requests.get(content[-1]['next'], auth=(bitbucketUser, bitbucketPass)))
    content.append(response[-1].json())
  for page in content:
    for branch in page['values']:
      repositoryBranches.append(branch['name'])
  return json.dumps(repositoryBranches)

#############################
# webhook related functions #
#############################

# find from wich repo the webhook has been sent
def _getRepoName(webhook):
  if 'name' in webhook['repository']:
    repo = webhook['repository']['name']
  else:
    repo = None
  return repo

# find from wich branch a webhook comes
def _getBranchName(webhook, action):
  if action == 'delete':
    name = webhook['push']['changes'][0]['old']['name']
  else:
    if action == 'create' or action == 'commit':
      name = webhook['push']['changes'][0]['new']['name']
    else:
       name = None
  try:
    delimiterPos = version.index('origin/')
    if delimiterPos != -1:
      name = name[8:]
  except:
    name = name
  return name

# find wich action is perfomed in a webhook : a commit, a branch creation or a branch delete
def _getAction(webhook):
  if 'new' in webhook['push']['changes'][0]:
    if 'old' in webhook['push']['changes'][0]:
      action = 'commit'
    else:
      action = 'create'
  else:
    if 'old' in webhook['push']['changes'][0]:
      action = 'delete'
    else:
      action = None
  return action

# return the friendly name of the commit in a given webhook
def _getCommitID(webhook):
  if 'new' in webhook['push']['changes'][0]:
    commitID = webhook['push']['changes'][0]['new']['target']['hash'][:7]
  else:
    commitID = None
  return commitID

# return a version number ("branch_name"-"friendly_commit_id")extracted from a webhook, called only when the triggered pipeline has a $version$ variable
def _getTargetVersion(webhook):
  if 'new' in webhook['push']['changes'][0]:
    version = webhook['push']['changes'][0]['new']['name']+'-'+webhook['push']['changes'][0]['new']['target']['hash'][:7]
  else:
    if 'old' in webhook['push']['changes'][0]:
      version = webhook['push']['changes'][0]['old']['name']+'-'+webhook['push']['changes'][0]['new']['target']['hash'][:7]
  try:
    delimiterPos = version.index('/') + 1
    if delimiterPos != 0:
      version = version[delimiterPos:]
  except:
    version = version
  return version

##################
# misc functions #
##################

# check if the data received is a valid json
def _isJson(data):
  try:
    json_object = json.loads(data)
  except ValueError, e:
    return False
  return True

# read the pipeline list from the configuration file

def _getPipelines(list):
  if Path(list).is_file():
    pipelineListFile = open(list, 'r')
  else:
    print "E: can't open list file"+list
    return '{ "error": "cannot open list file "'+list+' }'
  pipelines = json.load(pipelineListFile)
  return json.dumps(pipelines)

# return the pipeline available for a given context
def _getPipeline(repo, branch, action):
  global availablePipelines
  try:
    delimiterPos = branch.index('/')
    if delimiterPos != -1:
      inputBranch = branch[:delimiterPos]
  except:
    inputBranch = branch
  for id in availablePipelines:
    if availablePipelines[id]['repo'] == repo and availablePipelines[id]['action'] == action:
      try:
        delimiterPos = availablePipelines[id]['branch'].index('/')
        availableBranch = availablePipelines[id]['branch'][:delimiterPos]
        if availableBranch == inputBranch:
          pipeline = availablePipelines[id]
          pipeline['id'] = id
        else:
          pipeline = '{ }'
      except:
        if availablePipelines[id]['branch'] == branch:
          pipeline = availablePipelines[id]
          pipeline['id'] = id
        else:
          pipeline = '{ }'
      return json.dumps(pipeline)
  pipeline = '{ }'
  return json.dumps(pipeline)

# add a pipeline with given parameter
def _addPipeline(pipeline):
  global availableBranches
  global availablePipelines
  global availableRepositories
  newPipeline = json.loads(pipeline)
  maxCurrentID = 0
  if 'repo' not in newPipeline:
    return '{ "error": "repository not specified" }'
  if 'branch' not in newPipeline:
    return '{ "error": "branch not specified" }'
  if 'action' not in newPipeline:
    return '{ "error": "action not specified" }'
  if 'job' not in newPipeline:
     return '{ "error": "job not specified" }'
  if 'parameters' not in newPipeline:
    return '{ "parameters": "job not specified" }'
  for ppl in availablePipelines:
    if newPipeline['repo'] == availablePipelines[ppl]['repo']:
      if newPipeline['branch'] == availablePipelines[ppl]['branch']:
        if newPipeline['action'] == availablePipelines[ppl]['action']:
          if newPipeline['job'] == availablePipelines[ppl]['job']:
            if newPipeline['parameters'] == availablePipelines[ppl]['parameters']:
              return '{ "error": "pipeline already exists" }'
  if newPipeline['repo'] not in availableRepositories:
    return '{ "error": "repository specified not available" }'
  newPipelineID = _getNewPipelineID()
  availablePipelines[newPipelineID] = newPipeline
  pipelineListFile = open(pipeline_list_filename, 'w')
  pipelineListFile.write(json.dumps(availablePipelines, indent=2, sort_keys=True))
  pipelineListFile.close()
  newPipeline['id'] = newPipelineID
  print json.dumps(newPipeline)
  return '{ "OK": "pipeline <'+str(newPipeline['id'])+'> created" }'

def _deletePipeline(pipelineID):
  global availablePipelines
  try:
    availablePipelines.pop(pipelineID)
  except KeyError:
    return '{ "error": "pipeline <"'+str(pipelineID)+'> does not exists" }'
  pipelineListFile = open(pipeline_list_filename, 'w')
  pipelineListFile.write(json.dumps(availablePipelines, indent=2, sort_keys=True))
  pipelineListFile.close()
  return '{ "OK": "pipeline <'+str(pipelineID)+'> deleted" }'

# replace vars by context value in a pipeline, return a pipeline ready for execution
def _populatePipeline(pipeline, webhook):
  for parameter in pipeline['parameters']:
    if pipeline['parameters'][parameter].find('$') != -1:
      pipeline['parameters'][parameter] = pipeline['parameters'][parameter].replace('$repo$', _getRepoName(webhook))
      pipeline['parameters'][parameter] = pipeline['parameters'][parameter].replace('$action$', _getAction(webhook))
      pipeline['parameters'][parameter] = pipeline['parameters'][parameter].replace('$branch$', _getBranchName(webhook, _getAction(webhook)))
      pipeline['parameters'][parameter] = pipeline['parameters'][parameter].replace('$commit$', _getCommitID(webhook))
      pipeline['parameters'][parameter] = pipeline['parameters'][parameter].replace('$version$', _getTargetVersion(webhook))
  return pipeline

# return the  highest id available in the pipeline list +1
def _getNewPipelineID():
  global availablePipelines
  highestID = 0
  for id in availablePipelines:
    if int(id) > highestID:
      highestID = int(id)
  return highestID +1

###########################
# flask routes definition #
###########################

app = Flask(__name__)

# define the root route "/", webhooks are posted on this URL
@app.route('/', methods=['POST'])
def index():
  if _isJson(request.data):
    webhook = json.loads(request.data)
    print json.dumps(webhook, indent=2, sort_keys=True)
    repo = _getRepoName(webhook)
    action = _getAction(webhook)
    if repo != None and action!= None:
      branch = _getBranchName(webhook, action)
      if branch != None:
        pipelineTriggered = json.loads(_getPipeline(repo, branch, action))
        print 'webhook received : repo='+repo+', branch='+branch+', action='+action+'\n'
        if 'job' in pipelineTriggered:
          if pipelineTriggered['job'] in availableJobs:
            pipelineReady = _populatePipeline(pipelineTriggered, webhook)
            _startJenkinsJob(jenkinsServer, pipelineReady)
          return app.response_class('{ "OK": "pipeline "'+pipelineTriggered['id']+' started }', content_type='application/json'), 200
        else:
          print 'no pipeline to trigger on this action'
          return app.response_class('{ "OK": "no pipeline available for this webhook ('+repo+'-'+branch+'-'+action+')" }', content_type='application/json'), 200
      else:
        print 'E: branch identifier not found in the given webhook'
        return app.response_class('{ "error": "branch not found in the webhook" }', content_type='application/json'), 404
    else:
      print 'E: repo or action not found in the given webhook'
      return app.response_class('{ "error": "repository or action not found in the webhook" }', content_type='application/json'), 404
  else:
    print 'E: webhook is not a valid json'
    return app.response_class('{ "error": "webhook is not a valid json" }', content_type='application/json'), 415

# list configured pipelines
@app.route('/pipelines', methods=['GET'])
def getPipelines():
  pipelines = json.loads(_getPipelines(pipeline_list_filename))
  return app.response_class(json.dumps(pipelines), content_type='application/json'), 200

# get pipeline configured for given context
@app.route('/pipeline', methods=['GET'])
def getPipeline():
  pipeline = json.loads(_getPipeline(request.args.get('repo'), request.args.get('branch'), request.args.get('action')))
  if 'repo' in pipeline and 'id' in pipeline:
    return app.response_class(json.dumps(pipeline), content_type='application/json'), 200
  return app.response_class(json.dumps(pipeline), content_type='application/json'), 404

# add a pipeline
@app.route('/pipeline', methods=['POST'])
def postPipeline():
  if not _isJson(request.data):
    return app.response_class('{ "error": "pipeline received is not a valid json" }', content_type='application/json'), 415
  newPipeline = json.loads(request.data)
  return app.response_class(_addPipeline(json.dumps(newPipeline)), content_type='application/json'), 200

# delete a pipeline
@app.route('/pipeline', methods=['DELETE'])
def deletePipeline():
  deletion = _deletePipeline(request.args.get('id'))
  if 'OK' in deletion:
    return app.response_class(deletion , content_type='application/json'), 200
  else:
    return app.response_class(deletion , content_type='application/json'), 404

# get list of available repos
@app.route('/repositories', methods=['GET'])
def getRepositories():
  return app.response_class(json.dumps(availableRepositories.keys()), content_type='application/json'), 200

# refresh repository list from bitbucket
@app.route('/repositories/refresh', methods=['GET'])
def getRefreshRepository():
  availableRepositories = json.loads(_getAvailableRepos(False))
  return app.response_class(json.dumps(availableRepositories.keys()), content_type='application/json'), 200

# get available branches for a given repository
@app.route('/branches', methods=['GET'])
def getBranches():
  repo = request.args.get('repo')
  if repo in availableRepositories:
    if repo in availableBranches:
      return app.response_class(json.dumps(availableBranches[repo]), content_type='application/json'), 200
    else:
      availableBranches[repo] = _getAvailableBranches(repo, True)
      return app.response_class(json.dumps(availableBranches[repo]), content_type='application/json'), 200
  return app.response_class('{ "error": "no branches found or repository is unknown" }', content_type='application/json'), 404

# refresh available branches list for a given repository, then updat the branches cache
@app.route('/branches/refresh', methods=['GET'])
def getRefreshBranches():
  repo = request.args.get('repo')
  if repo in availableRepositories:
    global availableBranches
    availableBranches[repo] = json.loads(_getAvailableBranches(repo, False))
    branchesCacheFile = open(branchesCacheFileName, 'w')
    branchesCacheFile.write(json.dumps(availableBranches))
    branchesCacheFile.close()
    return app.response_class(json.dumps(availableBranches[repo]), content_type='application/json'), 200
  return app.response_class('{ "error": "no branches found or repository is unknown" }', content_type='application/json'), 404

# list available jenkins jobs
@app.route('/jobs', methods=['GET'])
def getJobs():
  return app.response_class(_getAvailablejobs(jenkinsServer), content_type='application/json'), 200

# get the a list of parameters from a given jenkins job name
@app.route('/parameters', methods=['GET'])
def getJobParameters():
  job = request.args.get('job')
  if job in availableJobs:
    return app.response_class(_getJobParameters(jenkinsServer, job), content_type='application/json'), 200
  return app.response_class('{ "error": "unknown job name" }', content_type='application/json'), 404

####################
# execution time ! #
####################

if __name__ == '__main__':
# connecting to the jenkins server and get job list
  jenkinsServer = jenkins.Jenkins(jenkinsServerURL)
  availableJobs = _getAvailablejobs(jenkinsServer)

# loading pipeline list
  if pipeline_list_filename.is_file():
    availablePipelines = json.loads(_getPipelines(pipeline_list_filename))
  else:
    availablePipelines = '{ }'
    open(pipeline_list_filename, 'a').close()

# getting reopsitory list
  bitbucketUser, bitbucketPass, bitbucketSlug = _connectToBitbucket(bitbucket_credentials_filename)
  availableRepositories = json.loads(_getAvailableRepos(True))

# getting list of branch per repository, from the cache if possible, or from the bitbucket API
  if Path(branchesCacheFileName).is_file():
    branchesCacheFile = open(branchesCacheFileName, 'r')
    availableBranches = json.load(branchesCacheFile)
    print 'branches loaded from cache'
  else:
    availableBranches = {}
    for repository in availableRepositories:
      availableBranches[repository] = json.loads(_getAvailableBranches(repository, True))
    branchesCacheFile = open(branchesCacheFileName, 'w')
    branchesCacheFile.write(json.dumps(availableBranches))
    branchesCacheFile.close()

# starting the webserver
  app.run(debug=False, host='0.0.0.0', port=listenPort)

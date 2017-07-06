# bitbucket-to-jenkins
An API oriented webserver used to manage links between bitbucket webhooks and jenkins jobs

Availables endpoints are :

	- GET /pipelines : return the list of available pipelines
		- http://10.250.0.14:8081/pipelines
		
	- GET /pipeline(URL:repo, URL:branch, URL:action) : return available pipeline for a given context
		- http://10.250.0.14:8081/pipeline?repo=REPO_NAME&branch=BANCH_NAME&action=commit
	
	- POST /pipeline(BODY:pipeline) : add a pipeline
		-  http://10.250.0.14:8081/pipeline, data = { "repo": "REPO_NAME", "branch": "BANCH_NAME", "action": "commit", "job": "JOB_NAME", "parameters": { "param1": "value1" } }
		
	- DELETE /pipeline(URL:id) : delete a pipeline
		- http://10.250.0.14:8081/pipeline?id=3
		
	- GET /repositories : return the list of repositories available on bitbucket
		- http://10.250.0.14:8081/repositories
		
	- GET /repositories/refresh : refresh reposirotry list from bitbucket API
		- http://10.250.0.14:8081/repositories/refresh
		
	- GET /branches(URL:repo) : return the branch list of a given repository
		- http://10.250.0.14:8081/branches?repo=REPO_NAME
		
	- GET /branches/refresh(URL:repo) : refresh the branch list of a given repository from bitbucket API
		- http://10.250.0.14:8081/branches/refresh?repo=REPO_NAME
	
	- GET /jobs : return the list of available jobs on jenkins
		- http://10.250.0.14:8081/jobs
		
	- GET /parameters(URL:job) : return the list of parameters available for a given job
		- http://10.250.0.14:8081/parameters?job=JOB_NAME

A pipeline is described as a following object :
```
{
  "repo": "Name of the followed repo",
  "branch": "name of the followed branch",
  "action": "action on the branch triggering the pipeline : creation of a branch(create), commit(commit), delete of a branch(delete)",
  "job": "name of the jenkins job to trigger",
  "parameters": {
    "param": "collection of parameters fot the jenkins job"
    }
}
```
Supported variables :
```
	- $repo$ : name of the repo emmiting the webhook
	- $branch$ : name of the impacted branch
	- $commit$: friendly name of the commit wich trigger the webhook event
	- $action$: action done on the branch
	- $version$: version number extracted from the branch name (ex: "release/1.2.3" -> "1.2.3")
```
Exemple : if a commit with the friendly id "1234567" is done on the branch "release/2.4.0" of the repo "vegetables", then the parameter 
```
"archive_name": "$repo$-$version$-$commit$.tar.gz" 
```
will be passed to jenkins as :
```
"archive_name": "vegetables-2.4.0-1234567.tar.gz"
```

pipeline {
    agent any
      environment {
        DOCKER_IMAGE = 'evplug-mobile-image'
        DOCKER_CONTAINER_NAME = 'evplug-mobile-app'
    }

    stages {
        stage('Checkout') {
            steps {
                // Checkout the source code from the GitHub repository
                checkout scm
            }
        }
        stage('Build Docker Image') {
            steps {
                script {
                    // Build a Docker image from the Dockerfile in the repository
                  sh  "docker build --no-cache -t dcr.mindzbase.tech/${DOCKER_IMAGE}:1.0.${env.BUILD_NUMBER} ."
                }
            }
        }
        stage('Pushing Docker Image to Private Docker Registry') {
            steps {
                // Define the remote server's IP address and SSH credentials
                script {
                   
                  sh "docker login dcr.mindzbase.tech -u marketa -p marketa123#"
                  sh "docker push dcr.mindzbase.tech/${DOCKER_IMAGE}:1.0.${BUILD_NUMBER}"

                    // Additional steps can be added here, such as verification or testing
                }
            }
        }

        stage('Cleaning all Stopped Docker Containers') {
            steps {
                    sh '''
                        # Fetch IDs of all containers in the exited state
                        exited_containers=$(docker ps -a -f status=exited -q)

                        # Check if there are any containers to remove
                        if [ -z "$exited_containers" ]; then
                            echo "No exited containers found."
                        else
                            # Remove the exited containers
                            docker rm $exited_containers
                            echo "Exited containers removed."
                        fi'''
                }
        }
        
        stage('Updating/Deploying new Evplug Mobile Server Container') {
            steps {
                
                script {
                   
                    sh '''echo "Deleting Existing Evplug Mobile Server Container"
                        echo "=================================="
                        current_container=$(docker ps|grep evplug-mobile-app|gawk \'{print $1}\')
                        if [ "$current_container" = "" ];
                        then
                            echo "No Container of evplug-mobile-app is running. Starting new evplug-mobile-app container now"
                            echo ""
                            echo ""
                            docker run -d --name ${DOCKER_CONTAINER_NAME} -p 14080:80 -p 14876:8765 -p 14880:8080 -v /root/evplug_conf/mobile/mobile_env:/app/.env -v /root/evplug_conf/mobile/evplug-prod.json:/app/evplug-prod.json -v /root/evplug_conf/mobile/wheelsdrive-config.json:/app/wheelsdrive-config.json --restart always dcr.mindzbase.tech/${DOCKER_IMAGE}:1.0.${BUILD_NUMBER}
                            
                        else
                            echo "Evplug Mobile Server Container exists. Updating it with new version of the Docker Image."
                            echo "Stopping and removing existing Evplug Mobile Server Container"
                            echo ""
                            echo "=================================="
                            echo ""
                            docker container stop $(echo $current_container)
                            docker container rm $(echo $current_container)
                            echo ""
                            echo ""
                            echo ""
                            echo "Installing new Evplug Mobile Server Container with newly built image"
                            echo ""
                            echo "=================================="
                            echo ""
                            docker run -d --name ${DOCKER_CONTAINER_NAME} -p 14080:80 -p 14876:8765 -p 14880:8080 -v /root/evplug_conf/mobile/mobile_env:/app/.env -v /root/evplug_conf/mobile/evplug-prod.json:/app/evplug-prod.json -v /root/evplug_conf/mobile/wheelsdrive-config.json:/app/wheelsdrive-config.json --restart always dcr.mindzbase.tech/${DOCKER_IMAGE}:1.0.${BUILD_NUMBER}
                         fi'''   

                    // Additional steps can be added here, such as verification or testing
                }
            }
        }
    }

    post {
        success {
            echo 'Evplug Mobile Server Container successfully completed! Access it at https://evmobile.mindzbase.tech/'
        }
        failure {
            echo 'Pipeline failed! - Please check logs for error'
        }
    }
}

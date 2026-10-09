pipeline {
    agent any
    stages {
        stage('Build') {
            steps {
                echo 'Building the application...'
            }
        }
        stage('Test') {
            steps {
                bat 'python -m pytest app\\tests'
            }
        }
        stage('Deploy') {
            steps {
                bat 'docker compose -f compose-demo\\docker-compose.yml up -d --build'
            }
        }
    }
}

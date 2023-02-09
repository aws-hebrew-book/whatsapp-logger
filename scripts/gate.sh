#!/bin/bash
# The following bash script is used to perform linting and formatting checks for a collection of projects.
# and it can be run to validate the code before committing it to the repository.


pushd admin-panel
poetry poe gate
popd

pushd cdk
poetry poe gate
popd

pushd googlesheet-recorder
poetry poe gate
popd

pushd googlesheet-recorder
poetry poe gate
popd

pushd whatsapp-web-listener
npm run prettier
npm run lint
popd
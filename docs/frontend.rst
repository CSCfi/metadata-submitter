.. _`frontend`:

Metadata Submitter Frontend
===========================

.. note:: Requirements:

    * Node 16+

Environment Setup
-----------------

The frontend can utilise the following env variables.

+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ENV                            | Default                       | Description                                                                       |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``NODE_ENV``                   | ``-``                         | Set to ``development``, if running in development mode.                           |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| ``REACT_APP_BACKEND_PROXY``    | ``localhost:5430``            | Proxy frontend requests to this backend, port must be specified.                  |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+
| Cypress.env ``port``           | ``3000``                      | Port Cypress can use for integration tests. Can be set in ``cypress.json``        |
+--------------------------------+-------------------------------+-----------------------------------------------------------------------------------+


Install and run
---------------

For installing ``metadata-submitter`` frontend do the following:

.. code-block:: console

    $ git clone https://github.com/CSCfi/metadata-submitter-frontend
    $ npm install

To run the frontend from command line use:

.. code-block:: console

    $ npm start

After installing and running, frontend can be found from ``http://localhost:3000``.

.. hint:: Some functionality in frontend requires a working backend.
          Follow the instructions in :ref:`deploy` for setting it up.


Internal structure
------------------

Reusable components are stored in ``src/components`` and views in ``src/views``. 
View-components reflect page structure, such as ``/``, ``/newdraft``, ``/login`` etc. 
One should not define and export views to be rendered inside other views, but rather always build views using components.

React Router is used to render different views in App-component. All components are wrapped with `Nav` which provider app menu and navigation.

Form components
---------------

Form components are crucial part of the application:

- All submissions are made with `react-hook-form <https://react-hook-form.com/>`_.
  Latter uses form as a reference so submission can be triggered outside the form. JSON schema based forms are created with custom JSON schema parser, which builds 
  ``react-hook-form`` based forms from given schema. The forms are validated against the JSON schema with ``Ajv``. 
  React-hook-form is used for performance reasons: it uses uncontrolled components so adding a lot of fields to array doesn't slow rendering of the application.

Constants
---------

Folder ``src/constants`` holds all the constants used in the application. The constants are uniquely defined and separated into different files according to its related context. For example, the file ``constants/wizardObject.js`` contains unique constants regarding to ``wizardObject`` such as: ``ObjectTypes, ObjectStatus, etc.``

The purposes of using these `constants` are:

- to avoid hard coding the values of variables repeatedly
- to keep the consistency when defining the values of variables
- to reuse those predefined values across the application

Example of defining and using a constant:

- First, define the constant object ``ObjectSubmissionTypes`` in ``constants/wizardObject.js``

.. code-block:: javascript

    export const ObjectSubmissionTypes = {
    form: "Form",
    xml: "XML",
    existing: "Existing",
    }


- Then, use this constant in `WizardComponents/WizardObjectIndex`:

.. code-block:: javascript

    import { ObjectSubmissionTypes } from "constants/wizardObject"

    switch (currentSubmissionType) {
        case ObjectSubmissionTypes.form: {
        target = "form"
        break
        }
        case ObjectSubmissionTypes.xml: {
        target = "XML upload"
        break
        }
        case ObjectSubmissionTypes.existing: {
        target = "drafts"
        break
        }
    }


Commonly used data types
------------------------

All commonly used data types of variables are defined in the file ``index.js`` in submission ``src/types``. The purposes are:

- to avoid hard coding the same data types frequently in different files
- to keep track and consistency of the data types across different files

For example:

- declare and export these data types in ``src/types/index.js``

.. code-block:: javascript

    export type ObjectInsideSubmission = {
    accessionId: string,
    schema: string,
    }

    export type ObjectTags = {
    submissionType: string,
    fileName?: string,
    }

    export type ObjectInsideSubmissionWithTags = ObjectInsideSubmission & { tags: ObjectTags }


- import and reuse the data types in different files:
- Reuse type ``ObjectInsideSubmission`` in ``features/wizardSubmissionSlice.js``:

.. code-block:: javascript

    import type { ObjectInsideSubmission } from "types"

    export const addObjectToSubmission = (
    submissionID: string,
    objectDetails: ObjectInsideSubmission
    ) => {}

    export const addObjectToDrafts = (
    submissionID: string,
    objectDetails: ObjectInsideSubmission
    ) => {}


- Reuse type ``ObjectInsideSubmissionWithTags`` consequently in both ``WizardComponents/WizardSavedObjectsList.js`` and ``WizardSteps/WizardShowSummaryStep.js``:

.. code-block:: javascript

    import type { ObjectInsideSubmissionWithTags } from "types"

    type WizardSavedObjectsListProps = { submissions: Array<ObjectInsideSubmissionWithTags> }


.. code-block:: javascript

    import type { ObjectInsideSubmissionWithTags } from "types"

    type GroupedBySchema = {| [Schema]: Array<ObjectInsideSubmissionWithTags> |}


Redux store
-----------

Redux is handled with `Redux Toolkit <https://redux-toolkit.js.org/>`_ and app is using following redux toolkit features:

- Store, global app state, configured in ``store.js``
- Root reducer, combining all reducers to one, configured in ``rootReducer.js``
- Slices with ``createSlice``-api, defining all reducer functions, state values and actions without extra boilerplate.
  - Slices are configured for different features in ``features/`` -submission.
  - Async reducer functions are also configured inside slices.

Examples for storing and dispatching with async submission function:

.. code-block:: javascript

    import { useSelector, useDispatch } from "react-redux"
    import { createNewDraftSubmission } from "features/SubmissionSlice"

    // Create base submission (normally from form)
    const submission = {
    name: "Test",
    description: "Test description for very best submission."
    }

    // Initialize dispatch with hook
    const dispatch = useDispatch()

    // Dispatch the action with submission
    dispatch(createNewDraftSubmission(submission))

    // Submission is now submitted to backend and added to redux store

    // Take submission from redux state, destructure and log values
    const submission = useSelector(state => state.Submission)
    const { id, name, description, metadataObjects } = submission
    console.log(id) // Should be id generated in backend
    console.log(name) // Should be name we set earlier
    console.log(description) // Should be description we set earlier
    console.log(metadataObjects) // Should be an empty array


Communicating with backend REST API
-----------------------------------

API/backend modules are defined in ``services/`` -folder with help from ``apisauce`` library. 
Modules should be only responsible for API-related things, so one shouldn't modify data inside them.

Example:

.. code-block:: javascript

    import { create } from "apisauce"

    const api = create({ baseURL: "/objects" })

    const createFromXML = async (objectType: string, XMLFile: string) => {
    let formData = new FormData()
    formData.append(objectType, XMLFile)
    return await api.post(`/${objectType}`, formData)
    }

    const createFromJSON = async (objectType: string, JSONContent: any) => {
    return await api.post(`/${objectType}`, JSONContent)
    }


Styles
------

App uses `Material UI <https://material-ui.com/>`_ components.

Global styles are defined with ``style.css`` and Material UI theme, customized for CSC. Material UI theme is set ``theme.js``, and added to ``index.js`` for use.

Styles are also used inside components, either with ``withStyles`` (modifies Material UI components) or ``makeStyles`` 
(creates css for component and its children). See `customizing components <https://material-ui.com/customization/components/>`_ for more info.

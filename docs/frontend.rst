.. _`frontend`:

Metadata Submitter Frontend
===========================

.. note:: Requirements:

    * Node 14+


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

.. hint:: Some functionality in frontend required a working backend.
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

- All submissions and folder creation are made with `react-hook-form <https://react-hook-form.com/>`_. 
  Latter uses form as a reference so submission can be triggered outside the form.
- Form for json schema based forms are created with custom json schema parser, which builds 
  ``react-hook-form`` based forms from given json schema. Json schema-based forms are validated against json schema with ``Ajv``. 
  React-hook-form is used for performance reasons: it uses uncontrolled components so adding a lot of fields to array doesn't slow rendering of the application.

Redux store
-----------

Redux is handled with `Redux Toolkit <https://redux-toolkit.js.org/>`_ and app is using following redux toolkit features:

- Store, global app state, configured in ``store.js``
- Root reducer, combining all reducers to one, configured in ``rootReducer.js``
- Slices with ``createSlice``-api, defining all reducer functions, state values and actions without extra boilerplate.
  - Slices are configured for different features in ``features/`` -folder.
  - Async reducer functions are also configured inside slices.

Examples for storing and dispatching with async folder function:

.. code-block:: javascript

    import { useSelector, useDispatch } from "react-redux"
    import { createNewDraftFolder } from "features/submissionFolderSlice"

    // Create base folder (normally from form)
    const folder = {
    name: "Test",
    description: "Test description for very best folder."
    }

    // Initialize dispatch with hook
    const dispatch = useDispatch()

    // Dispatch the action with folder
    dispatch(createNewDraftFolder(folder))

    // Folder is now submitted to backend and added to redux store

    // Take folder from redux state, destructure and log values
    const folder = useSelector(state => state.submissionFolder)
    const { id, name, description, metadataObjects } = folder
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

Global styles are defined with ``style.css`` and Material UI theme, customized for CSC. Material UI theme is set in ``index.js`` file.

Styles are also used inside components, either with ``withStyles`` (modifies Material UI components) or ``makeStyles`` 
(creates css for component and its children). See `customizing components <https://material-ui.com/customization/components/>`_ for more info.

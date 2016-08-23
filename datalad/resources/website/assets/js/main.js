/* global window */

// check if url exists
function url_exists(url) {
  var http = new XMLHttpRequest();
  http.open('HEAD', url, false);
  http.send();
  return http.status !== 404;
}

// construct parent path of url passed
function parent_url(url, node_name) {
  var turl = url.endsWith("/") ? url : url.concat("/");
  var url_array = turl.split(/[\\/]/);
  url_array.splice(-2, 1);
  return url_array.join('/');
}

// construct child path of url passed
function child_url(url, node_name) {
  return url.endsWith("/") ? url.concat(node_name) : url.concat('/').concat(node_name);
}

// replace direct calls to window.location with function
// will allow to mock tests for funcs using window.location
function loc(path) {
  return path ? path : window.location.pathname;
}

// decompose url to actual path to node
// e.g if next_url=d1/d2/d3 and
// current_url = example.com/ds/?dir=d1/d2
// return example.com/ds/d1/d2/d3
function absolute_url(next_url) {
  return (loc().replace(/\?.*/g, '') + next_url).replace('//', '/');
}

// extract GET parameters from URL
function getParameterByName(name, url) {
// refer https://stackoverflow.com/questions/901115/how-can-i-get-query-string-values-in-javascript
  if (!url) url = window.location.href;
  name = name.replace(/[\[\]]/g, "\\$&");
  var regex = new RegExp("[?&]" + name + "(=([^&#]*)|&|#|$)");
  var results = regex.exec(url);
  if (!results || !results[2]) return null;
  return decodeURIComponent(results[2].replace(/\+/g, " "));
}

// to update parameter if url directory or not dataset
function update_param_or_path(url, type, current_state) {
  // if url = root path(wrt index.html) then append index.html to url
  // allows non-root dataset dirs to have index.html
  // ease constrain on non-datalad index.html presence in dataset
  if (url === loc() || url === '/') {
    url = loc() + 'index.html';
    return false;
  } else if (type === 'file' || type === 'link')
    return false;
  else
    return true;
}

// construct path to metadata json based on directory to be rendered argument passed in url
function directory(jQuery, md5) {
  var metadata_dir = '.git/datalad/metadata/';
  var metadata_path = getParameterByName('dir') ?
        // remove basepath to directory
        getParameterByName('dir').replace(loc(), '')
        .replace(/^\/?/, '')    // replace beginning '/'
        .replace(/\/?$/, '') :  // replace ending '/'
        '/';
  var metadata_url = loc() + metadata_dir + md5(metadata_path);
  var parent = false;

  var table = jQuery('#directory').dataTable({
    async: true,    // async get json
    paging: false,  // ensure scrolling instead of pages
    ajax: {         // specify url to get json from ajax
      url: metadata_url,
      dataSrc: "nodes"
    },
    order: [[6, "desc"], [0, 'asc']],
    columns: [      // select columns and their names from json
      {data: "name", title: "Name"},
      {data: "date", title: "Last Modified", className: "dt-center", width: "20%"},
      {data: "size", title: "Size", className: "dt-center"},
      {data: null, title: "Description", className: "dt-center",
       render: function(data) { return ''; }},
      {data: "type", title: "Type", className: "dt-center", visible: false},
      {data: "path", title: "Path", className: "dt-center", visible: false},
      {data: null, title: "Sort", visible: false,
       render: function(data) {
         return (data.type === 'dir' || data.type === 'git' || data.type === 'annex');
       }}
    ],
    createdRow: function(row, data, index) {
      if (data.name === '..')
        parent = true;

      // show size = "ondisk size" / "total size"
      if (data.size.ondisk)
        jQuery('td', row).eq(2).html(data.size.ondisk + "/" + data.size.total);
      // if row is a directory append '/' to name cell
      if (data.type === 'dir' || data.type === 'git' || data.type === 'annex')
        jQuery('td', row).eq(0).html('<a>' + jQuery('td', row).eq(0).html() + '/</a>');
      if (data.name === '..')
        jQuery('td', row).eq(2).html('');
      for (var i = 0; i < 4; i++)  // attach css based on node-type to visible columns of each row
        jQuery('td', row).eq(i).addClass(data.type);
    },
    // add click handlers to each row(cell) once table initialised
    initComplete: function() {
      var api = this.api();
	// all tables should have ../ parent path
      if (!parent)
        api.row.add({name: "..", repo: "", date: "", path: "", type: "annex", size: ""}).draw();
      // add click handlers
      api.$('tr').click(function() {
        // extract its data json from table
        var data = api.row(this).data();
        // don't do anything for broken links
        if (data.type === 'link-broken')
          return;
        // get directory parameter
        var dir = getParameterByName('dir');
        // which direction to move, up or down the path ?
        var move = data.name === '..' ? parent_url : child_url;
        // which path to move, dir parameter or current path ?
        var next = dir ? move(dir, data.name) : move(absolute_url(''), data.name);
        // update parameter or url path with new path ?
        if (update_param_or_path(next, data.type, dir))
          window.location.search = '?dir=' + next.replace(loc(), '');
        else
          window.location.assign(next);
      });
    }
  });
  // api.columns([4, 5, 6]).visible(false);  // hide complete path, file type and sorting columns
  return table;
}

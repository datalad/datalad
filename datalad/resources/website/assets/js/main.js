/* global window XMLHttpRequest */

/**
 * check if url exists
 * @param {string} url url to test for existence
 * @return {boolean} returns true if url exists
 */
function url_exists(url) {
  var http = new XMLHttpRequest();
  http.open('HEAD', url, false);
  http.send();
  return http.status !== 404;
}

/**
 * construct parent path to current url
 * @param {string} url current url
 * @param {string} node_name clicked node name(not required)
 * @return {string} url to parent of current url
 */
function parent_url(url, node_name) {
  var turl = url.charAt(url.length - 1) === '/' ? url : url.concat("/");
  var url_array = turl.split(/[\\/]/);
  url_array.splice(-2, 1);
  return url_array.join('/');
}

/**
 * construct child path from current url and clicked node name
 * @param {string} url current url
 * @param {string} node_name clicked node name
 * @return {string} url to reach clicked node
 */
function child_url(url, node_name) {
  var turl = url.charAt(url.length - 1) === '/' ? url.slice(0, -1) : url;
  var tnode_name = node_name.charAt(0) === '/' ? node_name.slice(1) : node_name;
  return turl + '/' + tnode_name;
}

/**
 * if path given return path else return window.location.pathname
 * replaces direct calls to window.location with function
 * allows mocking tests for functions using window.location.pathname
 * @return {string} returns path to current window location
 */
function loc() {
  return window.location;
}

/**
 * decompose url to actual path to node
 * e.g if next_url = d1/d2/d3, current_url = example.com/ds/?dir=d1/d2
 * return example.com/ds/d1/d2/d3
 * @param {string} next_url name of GET parameter to extract value from
 * @return {string} returns path to node based on current location
 */
function absolute_url(next_url) {
  if (!next_url)
    return loc().pathname;
  else
    return (loc().pathname.replace(/\?.*/g, '') + next_url).replace('//', '/');
}

/**
 * extract GET parameters from URL
 * @param {string} name name of GET parameter to extract value from
 * @param {string} url url to extract parameter from
 * @return {string} returns the value associated with the `name` GET parameter if exists else null
 */
function getParameterByName(name, url) {
// refer https://stackoverflow.com/questions/901115/how-can-i-get-query-string-values-in-javascript
  if (!url) url = loc().href;
  name = name.replace(/[\[\]]/g, "\\$&");
  var regex = new RegExp("[?&]" + name + "(=([^&#]*)|&|#|$)");
  var results = regex.exec(url);
  if (!results || !results[2]) return null;
  return decodeURIComponent(results[2].replace(/\+/g, " "));
}

/**
 * Create Breadcrumbs to current location in dataset
 * @return {array} html linkified breadcrumbs array
 */
function bread2crumbs() {
  var raw_crumbs = loc().href.split('/');
  var crumbs = [];
  for (var index = 2; index < raw_crumbs.length() - 1; index++) {
    if (raw_crumbs[index] !== '?dir=')
      continue;
    var crumb_link = raw_crumbs.slice(0, index).join('/');
    crumbs.append('<a href=' + crumb_link + '>' + raw_crumbs[index] + '</a>');
  }
  return crumbs;
}

/**
 * update url parameter or url ?
 * @param {string} next_url next url to traverse to
 * @param {string} type type of clicked node
 * @param {string} current_state current node type. (variable unused)
 * @return {boolean} true if clicked node not root dataset
 */
function update_param_or_path(next_url, type, current_state) {
  // if url = root path(wrt index.html) then append index.html to url
  // allows non-root dataset dirs to have index.html
  // ease constrain on non-datalad index.html presence in dataset
  if (next_url === loc().pathname || next_url === '/' || !next_url)
    return false;
  else if (type === 'file' || type === 'link')
    return false;
  else
    return true;
}

/**
 * decide the url to move to based on current location and clicked node
 * @param {string} data data of clicked node
 * @param {string} url url to extract parameter from by getParameterByName
 * @return {Object} json contaning traverse type and traverse path
 */
function click_handler(data, url) {
  // don't do anything for broken links
  if (data.type === 'link-broken')
    return {next: '', type: 'none'};
  // get directory parameter
  var dir = getParameterByName('dir', url);
  // which direction to move, up or down the path ?
  var move = data.name === '..' ? parent_url : child_url;
  // which path to move, dir parameter or current path ?
  var next = dir ? move(absolute_url(dir), data.name) : move(absolute_url(''), data.name);
  // console.log(dir, move, next, update_param_or_path(next, data.type, dir));
  var traverse = {next: next, type: 'assign'};
  // if to update parameter, make next relative to index.html path
  if (update_param_or_path(next, data.type, dir))
    traverse = {next: '?dir=' + next.replace(loc().pathname, '/'), type: 'search'};
  // if clicked was current node '.', remove '.' at at end of next
  if (data.name === '.')
    traverse.next = traverse.next.slice(0, -1);
  return traverse;
}

/**
 * construct path to metadata json of node to be rendered
 * @param {object} md5 the md5 library object, used to compute metadata hash name of current node
 * @param {bool} parent if parent, find metadata json of parent directory instead
 * @return {string} path to the current node's metadata json
 */
function metadata_locator(md5, parent) {
  var metadata_dir = '.git/datalad/metadata/';
  var start_loc = absolute_url(getParameterByName('dir')).replace(/\/*$/, '/');

  // if parent argument set, find metadata json of parent directory instead
  var find_parent_ds = typeof parent !== 'undefined' ? parent : false;
  start_loc = find_parent_ds ? parent_url(start_loc).replace(/\/*$/, '/') : start_loc;
  var current_ds = start_loc;

  // traverse up directory tree till a dataset directory found
  // check by testing if current directory has a metadata directory
  while (!url_exists(current_ds + metadata_dir)) {
    // return error code, if no dataset found till root dataset
    if (current_ds.length <= loc().pathname.length)
      return '';
    // go to parent of current directory
    current_ds = parent_url(current_ds).replace(/^\/*/, '/').replace(/\/*$/, '/');
  }

  // if locating parent dataset or current_loc is a dataset, metadata filename = md5 of '/'
  if (start_loc === current_ds)
    return current_ds + metadata_dir + md5('/');

  // else compute name of current nodes metadata hash
  var metadata_path = getParameterByName('dir')
        .replace(current_ds
                 .replace(/\/$/, '')                // remove ending / from current_ds
                 .replace(loc().pathname, ''), '')  // remove basepath to dir
        .replace(/^\/*/, '')                        // replace beginning /'s
        .replace(/\/*$/, '');                       // replace ending /'s with /
  return current_ds + metadata_dir + md5(metadata_path);
}

/**
 * Retrieve metadata json of parent if exists
 * @param {string} jQuery jQuery library object
 * @param {string} md5 path of current dataset
 * @return {object} return metadata json object of parent if parent exists
 */
function parent_json(jQuery, md5) {
  var parent_metadata = metadata_locator(md5, true);

  // if parent dataset or parent metadata directory doesn't exist, return error code
  if (parent_metadata === '' || !url_exists(parent_metadata))
    return {};

  // else return required info for parent row from parent metadata json
  var parent_json_ = {};
  jQuery.ajax({
    url: parent_metadata,
    dataType: 'json',
    async: false,
    success: function(data) {
      parent_json_ = {name: '..',
                      date: data.date || '-',
                      path: data.path || '-',
                      type: data.type || 'dir',
                      size: size_renderer(data.size || null)};
    }
  });
  return parent_json_;
}

/**
 * render size of row entry based on size's present and their values
 * @param {object} size json object containing size info of current row entry
 * @return {string} return html string to be rendered in size column of current row entry
*/
function size_renderer(size) {
  // if size is undefined
  if (!size)
    return '-';
  // set ondisk_size = '-' if ondisk doesn't exist or = 0
  if (!size.ondisk || size.ondisk === '0 Bytes')
    size.ondisk = '-';
  // set total_size = '-' if total doesn't exist or = 0
  if (!size.total || size.total === '0 Bytes')
    size.total = '-';

  // show only one size, if both sizes present and identical
  if (size.ondisk === size.total)
    return size.total;
  // else show "ondisk size" / "total size"
  else
    return size.ondisk + "/" + size.total;
}

/**
 * render the datatable interface based on current node metadata
 * @param {object} jQuery jQuery library object
 * @param {object} md5 md5 library object
 * @return {object} returns the rendered DataTable object
 */
function directory(jQuery, md5) {
  var parent = false;

  var table = jQuery('#directory').dataTable({
    async: true,    // async get json
    paging: false,  // ensure scrolling instead of pages
    ajax: {         // specify url to get json from ajax
      url: metadata_locator(md5),
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

      // size rendering logic
      jQuery('td', row).eq(2).html(size_renderer(data.size));

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
      // all tables (except root ds) should have ../ parent path
      if (!parent) {
        var parent_meta = parent_json(jQuery, md5);
        if (!jQuery.isEmptyObject(parent_meta))
          api.row.add(parent_meta).draw();
      }
      // add click handlers
      api.$('tr').click(function() {
        var traverse = click_handler(api.row(this).data());
        if (traverse.type === 'assign')
          window.location.assign(traverse.next);
        else if (traverse.type === 'search')
          window.location.search = traverse.next;
      });
    }
  });
  return table;
}

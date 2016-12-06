/* global window XMLHttpRequest */
var metadataDir = '.git/datalad/metadata/';

/**
 * check if url exists
 * @param {string} url url to test for existence
 * @return {boolean} returns true if url exists
 */
function urlExists(url) {
  var http = new XMLHttpRequest();
  try {
    http.open('HEAD', url, false);
    http.send();
  } catch (err) {
    // seems to not work if subdir is not there at all. TODO
    return false;
  }
  return http.status !== 404;
}

/**
 * construct parent path to current url
 * @param {string} url current url
 * @param {string} nodeName clicked node name(not required)
 * @return {string} url to parent of current url
 */
function parentUrl(url, nodeName) {
  var turl = url.charAt(url.length - 1) === '/' ? url : url.concat("/");
  var urlArray = turl.split(/[\\/]/);
  urlArray.splice(-2, 1);
  return urlArray.join('/');
}

/**
 * construct child path from current url and clicked node name
 * @param {string} url current url
 * @param {string} nodeName clicked node name
 * @return {string} url to reach clicked node
 */
function childUrl(url, nodeName) {
  var turl = url.charAt(url.length - 1) === '/' ? url.slice(0, -1) : url;
  var tnodeName = nodeName.charAt(0) === '/' ? nodeName.slice(1) : nodeName;
  return turl + '/' + tnodeName;
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
 * e.g if nextUrl = d1/d2/d3, currentUrl = example.com/ds/?dir=d1/d2
 * return example.com/ds/d1/d2/d3
 * @param {string} nextUrl name of GET parameter to extract value from
 * @return {string} returns path to node based on current location
 */
function absoluteUrl(nextUrl) {
  if (!nextUrl)
    return loc().pathname;
  else
    return (loc().pathname.replace(/\?.*/g, '') + nextUrl).replace('//', '/');
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
  var rawCrumbs = loc().href.split('/');
  var spanClass = '<span class="dir">';
  var crumbs = [];
  for (var index = 2; index < rawCrumbs.length; index++) {
    if (rawCrumbs[index] === '?dir=')
      continue;
    var crumbLink = rawCrumbs.slice(0, index).join('/');
    if (index === rawCrumbs.length - 1)
      spanClass = '<span class="cwd">';
    crumbs.push('<a href=' + crumbLink + '/' + rawCrumbs[index] + '>' + spanClass +
		rawCrumbs[index] + '</span></a>');
  }
  return crumbs;
}

/**
 * Create installation RI
 * @return {string} RI to install current dataset from
 */
function uri2installri() {
  // TODO -- RF to centralize common logic with bread2crumbs
  var rawCrumbs = loc().href.split('/');
  var ri_ = '';
  // poor Yarik knows no JS
  // TODO:  now check for the last dataset is crippled, we would need
  // meld logic with breadcrumbs I guess, whenever they would get idea
  // of where dataset boundary is
  var ri = null;
  for (var index = 0; index < rawCrumbs.length; index++) {
    if (rawCrumbs[index] === '?dir=')
      continue;
    if (ri_)
      ri_ += '/';
    ri_ += rawCrumbs[index];
    if (urlExists(ri_ + '/' + metadataDir)) {
      ri = ri_;
    }
  }
  // possible shortcuts
  if (ri) {
    ri = ri.replace('http://localhost:8080', '//');   // for local debugging
    ri = ri.replace('http://datasets.datalad.org', '//');   // for deployment
  }
  return ri;
}

/**
 * update url parameter or url ?
 * @param {string} nextUrl next url to traverse to
 * @param {string} type type of clicked node
 * @param {string} currentState current node type. (variable unused)
 * @return {boolean} true if clicked node not root dataset
 */
function updateParamOrPath(nextUrl, type, currentState) {
  // if url = root path(wrt index.html) then append index.html to url
  // allows non-root dataset dirs to have index.html
  // ease constrain on non-datalad index.html presence in dataset
  if (nextUrl === loc().pathname || nextUrl === '/' || !nextUrl)
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
function clickHandler(data, url) {
  // don't do anything for broken links
  if (data.type === 'link-broken')
    return {next: '', type: 'none'};
  // get directory parameter
  var dir = getParameterByName('dir', url);
  // which direction to move, up or down the path ?
  var move = data.name === '..' ? parentUrl : childUrl;
  // which path to move, dir parameter or current path ?
  var next = dir ? move(absoluteUrl(dir), data.name) : move(absoluteUrl(''), data.name);
  // console.log(dir, move, next, updateParamOrPath(next, data.type, dir));
  var traverse = {next: next, type: 'assign'};
  // if to update parameter, make next relative to index.html path
  if (updateParamOrPath(next, data.type, dir))
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
function metadataLocator(md5, parent) {
  var startLoc = absoluteUrl(getParameterByName('dir')).replace(/\/*$/, '/');

  if (startLoc === '/' && parent) {
    return "";
  }

  // if parent argument set, find metadata json of parent directory instead
  var findParentDs = typeof parent !== 'undefined' ? parent : false;
  startLoc = findParentDs ? parentUrl(startLoc).replace(/\/*$/, '/') : startLoc;
  var currentDs = startLoc;

  // traverse up directory tree till a dataset directory found
  // check by testing if current directory has a metadata directory
  while (!urlExists(currentDs + metadataDir)) {
    // return error code, if no dataset found till root dataset
    if (currentDs.length <= loc().pathname.length)
      return '';
    // go to parent of current directory
    currentDs = parentUrl(currentDs).replace(/^\/*/, '/').replace(/\/*$/, '/');
  }

  // if locating parent dataset or current_loc is a dataset, metadata filename = md5 of '/'
  if (startLoc === currentDs)
    return currentDs + metadataDir + md5('/');

  // else compute name of current nodes metadata hash
  var metadataPath = getParameterByName('dir')
        .replace(currentDs
                 .replace(/\/$/, '')                // remove ending / from currentDs
                 .replace(loc().pathname, ''), '')  // remove basepath to dir
        .replace(/^\/*/, '')                        // replace beginning /'s
        .replace(/\/*$/, '');                       // replace ending /'s with /
  return currentDs + metadataDir + md5(metadataPath);
}

/**
 * Retrieve metadata json of parent if exists
 * @param {string} jQuery jQuery library object
 * @param {string} md5 path of current dataset
 * @return {object} return metadata json object of parent if parent exists
 */
function parentJson(jQuery, md5) {
  var parentMetadata = metadataLocator(md5, true);

  // if parent dataset or parent metadata directory doesn't exist, return error code
  if (parentMetadata === '' || !urlExists(parentMetadata))
    return {};

  // else return required info for parent row from parent metadata json
  var parentJson_ = {};
  jQuery.ajax({
    url: parentMetadata,
    dataType: 'json',
    async: false,
    success: function(data) {
      parentJson_ = {name: '..',
                      date: data.date || '-',
                      path: data.path || '-',
                      type: data.type || 'dir',
                      description: data.description || '',
                      size: sizeRenderer(data.size || null)};
    }
  });
  return parentJson_;
}

/**
 * render size of row entry based on size's present and their values
 * @param {object} size json object containing size info of current row entry
 * @return {string} return html string to be rendered in size column of current row entry
 */
function sizeRenderer(size) {
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
 * wrap and insert error message into html
 * @param {object} jQuery jQuery library object to insert message into DOM
 * @param {object} msg message to wrap and insert into HTML
 */
function errorMsg(jQuery, msg) {
  jQuery('#content').prepend(
    "<P> ERROR: " + msg + "</P>"
  );
}

/**
 * render the datatable interface based on current node metadata
 * @param {object} jQuery jQuery library object
 * @param {object} md5 md5 library object
 * @return {object} returns the rendered DataTable object
 */
function directory(jQuery, md5) {
  var parent = false;
  var md5Url = metadataLocator(md5);

  if (md5Url === "") {
    errorMsg(
        jQuery,
        "Could not find any metadata directory. Sorry.  Most probably cause is " +
        "that 'publish' didn't run the post-update hook"
    );
    return;
  }

  if (!urlExists(md5Url)) {
    errorMsg(
        jQuery,
        "Could not find metadata for current dataset. Sorry.  Most probably cause is " +
        "that 'publish' didn't run the post-update hook"
    );
    return;
  }

  // Embed the table placeholder
  jQuery('#content').prepend('<table id="directory" class="display"></table>');

  // add HOWTO install
  var ri = uri2installri();
  if (ri) {
    jQuery('#content').prepend(
        '<div id="installation">' +
        '<P>To install this dataset in your current directory use</P>' +
        '<span class="command">datalad install ' + ri + '</span>' +
        '<P>To install with all subdatasets and all data</P>' +
        '<span class="command">datalad install -r -g ' + ri + '</span>' +
        '<P style="font-size: 90%;">For more information about DataLad and installation instructions visit <a href="http://datalad.org">datalad.org</a></P>' +
        '</div>');
  }

  var table = jQuery('#directory').dataTable({
    async: true,    // async get json
    paging: false,  // ensure scrolling instead of pages
    ajax: {         // specify url to get json from ajax
      url: md5Url,
      dataSrc: "nodes"
    },
    order: [[6, "desc"], [0, 'asc']],
    columns: [      // select columns and their names from json
      {data: "name", title: "Name", width: "25%"},
      {data: "date", title: "Last Modified", className: "dt-center", width: "18%"},
      {data: "size", title: "Size", className: "dt-center", width: "18%"},
      {data: null, title: "Description", className: "dt-left",
       render: function(data) {
         var meta = data.metadata;
         if (!meta) return '';
         var desc = meta[0].name;
         return desc ? desc : '';
       }},
      {data: "type", title: "Type", className: "dt-center", visible: false},
      {data: "path", title: "Path", className: "dt-center", visible: false},
      {data: null, title: "Sort", visible: false,
       render: function(data) {
         return (data.type === 'dir' || data.type === 'git' || data.type === 'annex' || data.type === 'uninitialized');
       }},
      // make metadata searchable right there!
      {data: null, title: "Metadata", visible: false,
        render: function(data) {
          var meta = data.metadata;
          return meta ? JSON.stringify(meta) : "";
        }}
    ],
    createdRow: function(row, data, index) {
      if (data.name === '..')
        parent = true;

      // size rendering logic
      jQuery('td', row).eq(2).html(sizeRenderer(data.size));

      // if row is a directory append '/' to name cell
      if (data.type === 'dir' || data.type === 'git' || data.type === 'annex' || data.type === 'uninitialized') {
        var orig = jQuery('td', row).eq(0).html();
        orig = '<a>' + orig + '/</a>';
        if (data.tags) {
          orig = orig + "&nbsp;<span class='gittag'>@" + data.tags + "</span>";
        }
        jQuery('td', row).eq(0).html(orig);
      }
      if (data.name === '..')
        jQuery('td', row).eq(2).html('');
      for (var i = 0; i < 4; i++)  // attach css based on node-type to visible columns of each row
        jQuery('td', row).eq(i).addClass(data.type);
    },
    // add click handlers to each row(cell) once table initialised
    initComplete: function() {
      var api = this.api();
      // all tables should have ../ parent path except webinterface root
      if (!parent) {
        var parentMeta = parentJson(jQuery, md5);
        if (!jQuery.isEmptyObject(parentMeta))
          api.row.add(parentMeta).draw();
      }
      // add click handlers
      api.$('tr').click(function() {
        var traverse = clickHandler(api.row(this).data());
        if (traverse.type === 'assign')
          window.location.assign(traverse.next);
        else if (traverse.type === 'search')
          window.location.search = traverse.next;
      });
      // add breadcrumbs
      jQuery('#directory_filter').prepend('<span class="breadcrumb">' +
                                           bread2crumbs().join(' / ') +
                                          '</span>');
    }
  });
  return table;
}

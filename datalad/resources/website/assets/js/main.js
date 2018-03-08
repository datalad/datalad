/* global window XMLHttpRequest */
var metadataDir = '.git/datalad/metadata/';
var ntCache = {};   // node_path: type cache[dictionary]
/* might need (in)validation, e.g. while testing with local
   localhost:8000  it kept bringing install urls from previous
   sessions... obscure
   Or may be should be replaced with sessionStorage altogether
var stored = sessionStorage['ntCache'];
*/
var stored = localStorage['ntCache'];
if (stored) ntCache = JSON.parse(stored);

/**
 * check if url exists
 * @param {string} url url to test for existence
 * @return {boolean} returns true if url exists
 */
function urlExists(url) {
  var http = new XMLHttpRequest();
  try {
    // TODO: sync open seems to be deprecated.
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
  return decodeURIComponent(results[2]); // .replace(/\+/g, " "));
}

/**
 * Create Breadcrumbs to current location in dataset
 * @param {string} jQuery jQuery library object
 * @param {string} md5 to compute name of current dataset
 * @param {string} json metadata of current node
 * @return {array} html linkified breadcrumbs array
 */
function bread2crumbs(jQuery, md5) {
  var rawCrumbs = loc().href.replace(/\/$/, '').split('/');  // split, remove trailing '/'
  var spanClass = '<span class="dir">';
  var crumbs = [];
  for (var index = 2; index < rawCrumbs.length; index++) {
    if (rawCrumbs[index] === '?dir=')
      continue;
    rawCrumbs[index] = decodeURI(rawCrumbs[index]);
    var crumbLink = rawCrumbs.slice(0, index).join('/');
    var nextLink = crumbLink + '/' + rawCrumbs[index];
    // create span class of crumb based on node type it represents
    spanClass = '<span class="' + getNodeType(jQuery, md5, nextLink) + '">';
    crumbs.push('<a href=' + nextLink + '>' + spanClass + rawCrumbs[index] + '</span></a>');
  }
  return crumbs;
}

/*
Helper to check if cache has the item and the key for it set, get and set them
*/
function has_cached(item, key) {
    return (item in ntCache) && (key in ntCache[item]);
}
function get_cached(item, key) {
    return ntCache[item][key];
}
function set_cached(item, key, value) {
    var cache_rec = (item in ntCache) ? ntCache[item] : {};
    cache_rec[key] = value;
    ntCache[item] = cache_rec;
    return value;
}

/**
 * Create installation RI
 * @return {string} RI to install current dataset from
 */
function uri2installri() {
  // TODO -- RF to centralize common logic with bread2crumbs
  var href = loc().href;
  var rawCrumbs = href.split('/');
  var ri_ = '';

  var dir = getParameterByName('dir', href);
  var topurl = href.replace(/\?.*/, '').replace(/\/$/, '')

  if (has_cached(dir, "install_url")) return get_cached(dir, "install_url");

  if (has_cached(dir, "type")
      && ((ntCache[dir].type == 'git') || (ntCache[dir].type == 'annex'))) {
      ri = topurl + dir
  }
  else {
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
        // TODO: avoid direct query for urlExists and make use of the ntCache
        if (urlExists(ri_ + '/' + metadataDir)) {
          ri = ri_;
        }
      }
  }
  // possible shortcuts
  if (ri) {
    ri = ri.replace('http://localhost:8080', '//');   // for local debugging
    ri = ri.replace('http://datasets.datalad.org', '//');   // for deployment
  }
  set_cached(dir, "install_url", ri);
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
 * @return {Object} json containing traverse type and traverse path
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
  var traverse = {next: next, type: 'assign'};
  // if to update parameter, make next relative to index.html path
  if (updateParamOrPath(next, data.type, dir))
    /* encodeURIComponent would encode more https://stackoverflow.com/a/23842171 */
    traverse = {next: '?dir=' + encodeURI(next.replace(loc().pathname, '/')), type: 'search'};
  // if clicked was current node '.', remove '.' at at end of next
  if (data.name === '.')
    traverse.next = traverse.next.slice(0, -1);
  return traverse;
}

/**
 * construct path to metadata json of node to be rendered
 * @param {object} md5 the md5 library object, used to compute metadata hash name of current node
 * @param {bool} parent if parent, find metadata file of parent directory instead
 * @param {object} nodeurl if nodeurl, find metadata file wrt to node at nodeurl (default: current loc())
 * @return {string} path to the (default: current loc()) node's metadata file
 */
function metadataLocator(md5, parent, nodeurl) {
  // if path argument set, find metadata file wrt node at path directory
  var nodepath = typeof nodeurl !== 'undefined' ? nodeurl : loc().href;
  var startLoc = absoluteUrl(
                        getParameterByName('dir', nodepath))
                    .replace(/\/+$/, '');

  if (startLoc === '' && parent) return "";

  // if parent argument set, find metadata file of parent directory instead
  var findParentDs = typeof parent !== 'undefined' ? parent : false;
  startLoc = findParentDs ? parentUrl(startLoc) : startLoc;
  startLoc = startLoc.replace(/\/+$/, '');
  var currentDs = startLoc;
  var cacheKey = (findParentDs ? "%PARENT%" : "") + startLoc;
  // urlExists("http://localhost:8081/CHECK" + cacheKey)
  if (has_cached(cacheKey, "metadata_path")) return get_cached(cacheKey, "metadata_path");
  // traverse up directory tree till a dataset directory found
  // check by testing if current directory has a metadata directory
  while (!urlExists(currentDs + "/" + metadataDir)) {
    // return error code, if no dataset found till root dataset
    if (currentDs.length <= loc().pathname.length)
      return '';
    // go to parent of current directory
    currentDs = parentUrl(currentDs).replace(/^\/+/, '/').replace(/\/+$/, '');
  }

  // if locating parent dataset or current_loc is a dataset, metadata filename = md5 of '/'
  if (startLoc === currentDs) {
    var metadataPath = currentDs + '/' + metadataDir + md5('/');
  }
  else {
    // else compute name of current nodes metadata hash
    var metadataPath = getParameterByName('dir')
        .replace(currentDs
                 .replace(/\/$/, '')                // remove ending / from currentDs
                 .replace(loc().pathname, ''), '')  // remove basepath to dir
        .replace(/^\/+/, '')                        // replace beginning /'s
        .replace(/\/+$/, '');                       // replace ending /'s with /
    metadataPath = currentDs + "/" + metadataDir + md5(metadataPath);
  }
  return set_cached(cacheKey, "metadata_path", metadataPath);
}

/**
 * Retrieve metadata json of (parent of) node at path (default: current loc)
 * @param {string} jQuery jQuery library object
 * @param {string} md5 path of current dataset
 * @param {bool} parent if parent, find metadata json of parent directory instead
 * @param {bool} top if top, don't return children metadata
 * @param {string} nodeurl if nodeurl, find metadata json wrt node at nodeurl (default: loc().href)
 * @return {array} return metadata json and location of node's dataset, if it exists
 */
function nodeJson(jQuery, md5, parent, top, nodeurl) {
  // if path argument set, find metadata file wrt node at path directory, else current location
  // if parent argument set, find metadata json of parent directory instead
  var nodeMetaUrl = metadataLocator(md5, parent, nodeurl);

  // if node's dataset or node's metadata directory doesn't exist, return error code
  if (nodeMetaUrl === '' || !urlExists(nodeMetaUrl))
    return [{}, null];

  // else return required info for parent row from parent metadata json
  var nodeJson_ = {};
  jQuery.ajax({
    url: nodeMetaUrl,
    dataType: 'json',
    async: false,
    success: function(data) {
      var dname = parent ? ".." : data.name;
      nodeJson_ = top ? {name: dname || '-',
                         date: data.date || '-',
                         path: data.path || '-',
                         type: data.type || 'dir',
                         description: data.description || '',
                         size: sizeRenderer(data.size || null)}
                      : data;
    }
  });

  // extract relative url of current node's dataset
  var metaDirRegex = new RegExp(metadataDir + ".*", "g");
  var currentDs = nodeMetaUrl.replace(metaDirRegex, '').replace(loc().pathname, '/');
  return {js: nodeJson_, ds: currentDs};
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
 * get (and cache) the node type given its path and associated metadata json
 * @param {object} jQuery jQuery library object
 * @param {object} md5 md5 library object
 * @param {string} url leaf url to start caching from upto root
 * @param {object} json metadata json object
 * @return {string} returns the type of the node at path
 */
function getNodeType(jQuery, md5, url) {
  // convert url to cache key [url relative to root dataset]
  var relUrl = getParameterByName('dir', url) || '/';

  function abspathlen(url) {
    return url.replace(loc().search, '').replace(/\/$/, '').length;
  }

  // if outside root dataset boundary, return default node type
  if (abspathlen(loc().href) > abspathlen(url))
    return 'dir';

  // if key of url in current path, return cached node's type
  if (has_cached(relUrl, "type"))
    return ntCache[relUrl].type;

  // else get metadata json of node if no json object explicitly passed
  var temp = nodeJson(jQuery, md5, false, false, url);
  var metaJson = temp.js;
  var dsLoc = temp.ds;

  // return default type if no metaJson or relative_url
  if (!relUrl || !("path" in metaJson) || !("type" in metaJson)) return 'dir';

  // Find relative url of dataset of node at passed url
  // Crude method: Find name of the current dataset in the url passed
  // i.e if dataset_name = b, url = a/b/c, dataset_url = a/b
  // this will fail in case of multiple node's with same name as dataset in current url path
  // method of finding node's dataset url only used while testing (by passing json directly to func)
  if (!dsLoc) {
    // to ensure correct subpath creation, if ds name empty name or undefined
    metaJson.name = (!metaJson.name || metaJson.name === '') ? undefined : metaJson.name;
    var rx = new RegExp(metaJson.name + ".*", "g");
    dsLoc = relUrl.replace(rx, metaJson.name);
  }
  // cache type of all node's associated with node at url's dataset
  if ("nodes" in metaJson) {
    metaJson.nodes.forEach(function(child) {
      var childRelUrl = child.path !== '.' ? (dsLoc + '/' + child.path).replace(/\/\//, '/') : dsLoc;
      childRelUrl = childRelUrl.replace(/\/+$/, "");  // strip trailing /
      if (!(childRelUrl in ntCache))
        set_cached(childRelUrl, "type", child.type);
    });
  }
  if ("type" in metaJson) return metaJson.type;
  return (relUrl in ntCache) ? ntCache[relUrl].type : "dir";
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
    jQuery('#installation').prepend(
        '<P style="margin-top: 0px;">To install this dataset in your current directory use</P>' +
        '<span class="command">datalad install ' + ri + '</span>' +
        '<P style="font-size: 90%;">To install with all sub-datasets add <span class="command-option">-r</span>.' +
        '    To get all the data add <span class="command-option">-g</span>.' +
        '    To get data in parallel add <span class="command-option">-JN</span>, where <span class="command-option">N</span> would be the number of parallel downloads. ' +
        '<P style="font-size: 90%;">For more information about DataLad and installation instructions visit <a href="http://datalad.org">datalad.org</a></P>'
        );
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
         var desc = meta.title;
         if (!desc) desc = meta.name;
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
        var parentMeta = nodeJson(jQuery, md5, true, true).js;
        if (!jQuery.isEmptyObject(parentMeta))
          api.row.add(parentMeta).draw();
      }
      // add click handlers
      api.$('tr').click(function() {
        var traverse = clickHandler(api.row(this).data());
        if (traverse.type === 'assign')
          // window.location.assign(traverse.next);
          window.location.href = traverse.next;
        else if (traverse.type === 'search')
          window.location.search = traverse.next;
      });
      // add breadcrumbs
      jQuery('#directory_filter').prepend('<span class="breadcrumb">' +
                                          bread2crumbs(jQuery, md5).join(' / ') +
                                          '</span>');
    }
  });
  localStorage['ntCache'] = JSON.stringify(ntCache);
  return table;
}

/* triggers also when just opening a page... wanted to clear it upon forced
   refresh only

function clearCache() {
    localStorage['ntCache'] = '';
    urlExists('http://localhost:8081/CLEARED')
}

window.addEventListener('beforeunload', clearCache, false);
*/
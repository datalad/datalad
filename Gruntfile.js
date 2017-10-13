module.exports = function(grunt) {
  // Project configuration.
  grunt.initConfig({
    qunit: {
      files: ['datalad/resources/website/tests/test.html']
    }
  });
  // Load plugin
  grunt.loadNpmTasks('grunt-contrib-qunit');
  // Task to run tests
  grunt.registerTask('test', 'qunit');
};

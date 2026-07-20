fetch("projects.json")
  .then(response => response.json())
  .then(data => {
    const table = document.getElementById("projectsTable");

    data.forEach(project => {
      const row = table.insertRow();

      row.insertCell(0).innerText = project.project;
      row.insertCell(1).innerText = project.county;
      row.insertCell(2).innerText = project.status;
      row.insertCell(3).innerText = project.value;
      row.insertCell(4).innerText = project.opportunity;
    });
  });
